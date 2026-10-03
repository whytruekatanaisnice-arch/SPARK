"""Tasks and submissions: coach creates/reviews, student submits/reads feedback."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.task import Feedback, Submission, Task
from app.schemas.task import FeedbackCreate, FeedbackOut, SubmissionCreate, SubmissionOut, TaskCreate, TaskOut
from app.security import CurrentUser, require_coach, require_student

# ---------------- Coach side ----------------

coach_router = APIRouter(prefix="/api/coach", tags=["coach:tasks"], dependencies=[Depends(require_coach)])


@coach_router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    task = Task(**payload.model_dump(), created_by=current_user.id)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@coach_router.get("/tasks", response_model=list[TaskOut])
async def list_tasks_for_club(club_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.club_id == club_id).order_by(Task.created_at.desc()))
    return result.scalars().all()


@coach_router.get("/submissions", response_model=list[SubmissionOut])
async def list_submissions(task_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Submission).where(Submission.task_id == task_id).order_by(Submission.submitted_at.desc()))
    return result.scalars().all()


@coach_router.post("/feedback", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
async def give_feedback(payload: FeedbackCreate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
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
    submission = await db.get(Submission, submission_id)
    if not submission or submission.student_id != current_user.id:
        raise HTTPException(status_code=404, detail="Submission not found")

    result = await db.execute(select(Feedback).where(Feedback.submission_id == submission_id))
    return result.scalars().all()
