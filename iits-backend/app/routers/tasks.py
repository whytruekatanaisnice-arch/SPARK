"""Tasks and submissions: coach creates/reviews, student submits/reads feedback."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import demo_store
from app.database import get_db
from app.models.attendance import AttendanceSession
from app.models.club import Club
from app.models.task import Feedback, Submission, Task
from app.schemas.task import FeedbackCreate, FeedbackOut, SubmissionCreate, SubmissionOut, TaskCreate, TaskOut
from app.security import CurrentUser, require_coach, require_student
from app.models.user import UserRole

# ---------------- Coach side ----------------

coach_router = APIRouter(prefix="/api/coach", tags=["coach:tasks"], dependencies=[Depends(require_coach)])


@coach_router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        club = demo_store.get_record("clubs", str(payload.club_id))
        if not club:
            raise HTTPException(status_code=404, detail="Club not found")
        if current_user.role != UserRole.ADMIN and club.get("coach_id") != str(current_user.id):
            raise HTTPException(status_code=403, detail="You can only create tasks for your own clubs")
        task = jsonable_encoder(payload)
        task.update(created_by=str(current_user.id), created_at=datetime.now(timezone.utc).isoformat())
        return demo_store.create_record("tasks", task)

    club = await db.get(Club, payload.club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    if current_user.role != UserRole.ADMIN and club.coach_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only create tasks for your own clubs")
    if payload.session_id:
        session = await db.get(AttendanceSession, payload.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.club_id != payload.club_id:
            raise HTTPException(status_code=400, detail="Task session must belong to the selected club")
    task = Task(**payload.model_dump(), created_by=current_user.id)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@coach_router.get("/tasks", response_model=list[TaskOut])
async def list_tasks_for_club(
    club_id: UUID,
    current_user: CurrentUser,
    session_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    if demo_store.is_enabled():
        club = demo_store.get_record("clubs", str(club_id))
        if not club:
            raise HTTPException(status_code=404, detail="Club not found")
        if current_user.role != UserRole.ADMIN and club.get("coach_id") != str(current_user.id):
            raise HTTPException(status_code=403, detail="You can only view tasks for your own clubs")
        return [
            task for task in demo_store.collection("tasks")
            if task["club_id"] == str(club_id)
            and (session_id is None or task.get("session_id") == str(session_id))
        ]

    club = await db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    if current_user.role != UserRole.ADMIN and club.coach_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only view tasks for your own clubs")
    stmt = select(Task).where(Task.club_id == club_id)
    if session_id:
        session = await db.get(AttendanceSession, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.club_id != club_id:
            raise HTTPException(status_code=400, detail="Session does not belong to the selected club")
        stmt = stmt.where(Task.session_id == session_id)
    result = await db.execute(stmt.order_by(Task.created_at.desc()))
    return result.scalars().all()


@coach_router.get("/submissions", response_model=list[SubmissionOut])
async def list_submissions(task_id: UUID, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        return [
            item for item in demo_store.collection("submissions")
            if item["task_id"] == str(task_id)
        ]
    result = await db.execute(select(Submission).where(Submission.task_id == task_id).order_by(Submission.submitted_at.desc()))
    return result.scalars().all()


@coach_router.post("/feedback", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
async def give_feedback(payload: FeedbackCreate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        if demo_store.get_record("submissions", str(payload.submission_id)) is None:
            raise HTTPException(status_code=404, detail="Submission not found")
        feedback = jsonable_encoder(payload)
        feedback.update(coach_id=str(current_user.id), created_at=datetime.now(timezone.utc).isoformat())
        return demo_store.create_record("feedback", feedback)

    submission = await db.get(Submission, payload.submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    feedback = Feedback(**payload.model_dump(), coach_id=current_user.id)
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return feedback


# ---------------- Student side ----------------

student_router = APIRouter(prefix="/api/student", tags=["student:tasks"], dependencies=[Depends(require_student)])


@student_router.get("/tasks", response_model=list[TaskOut])
async def my_tasks(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        club_ids = {
            membership["club_id"]
            for membership in demo_store.collection("memberships")
            if membership["student_id"] == str(current_user.id) and membership.get("is_active", True)
        }
        return sorted(
            [task for task in demo_store.collection("tasks") if task["club_id"] in club_ids],
            key=lambda task: task.get("due_date") or "",
        )

    from app.models.club import ClubMembership

    club_ids_result = await db.execute(
        select(ClubMembership.club_id).where(ClubMembership.student_id == current_user.id, ClubMembership.is_active == True)  # noqa: E712
    )
    club_ids = [row[0] for row in club_ids_result.all()]
    if not club_ids:
        return []

    result = await db.execute(select(Task).where(Task.club_id.in_(club_ids)).order_by(Task.due_date))
    return result.scalars().all()


@student_router.post("/submissions", response_model=SubmissionOut, status_code=status.HTTP_201_CREATED)
async def submit_task(payload: SubmissionCreate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        if demo_store.get_record("tasks", str(payload.task_id)) is None:
            raise HTTPException(status_code=404, detail="Task not found")
        submission = jsonable_encoder(payload)
        submission.update(student_id=str(current_user.id), submitted_at=datetime.now(timezone.utc).isoformat())
        return demo_store.create_record("submissions", submission)

    task = await db.get(Task, payload.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    submission = Submission(**payload.model_dump(), student_id=current_user.id)
    db.add(submission)
    await db.commit()
    await db.refresh(submission)
    return submission


@student_router.get("/submissions/{submission_id}/feedback", response_model=list[FeedbackOut])
async def get_feedback(submission_id: UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        submission = demo_store.get_record("submissions", str(submission_id))
        if submission is None or submission["student_id"] != str(current_user.id):
            raise HTTPException(status_code=404, detail="Submission not found")
        return [
            item for item in demo_store.collection("feedback")
            if item["submission_id"] == str(submission_id)
        ]

    submission = await db.get(Submission, submission_id)
    if not submission or submission.student_id != current_user.id:
        raise HTTPException(status_code=404, detail="Submission not found")

    result = await db.execute(select(Feedback).where(Feedback.submission_id == submission_id))
    return result.scalars().all()
