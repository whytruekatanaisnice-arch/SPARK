"""Parent/guardian: view linked children's attendance, feedback, PAJSK standing."""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.attendance import AttendanceRecord, AttendanceSession
from app.models.notification import Notification
from app.models.task import Feedback, Submission
from app.models.user import ParentStudentLink, StudentProfile, User
from app.schemas.common import Message
from app.schemas.notification import NotificationOut
from app.schemas.report import PajskBreakdown
from app.security import CurrentUser, require_parent
from app.utils.pa_jsK import calculate_pa_jsK

router = APIRouter(prefix="/api/parent", tags=["parent"], dependencies=[Depends(require_parent)])


async def _assert_is_my_child(parent_id: UUID, student_id: UUID, db: AsyncSession) -> None:
    link = await db.execute(
        select(ParentStudentLink).where(ParentStudentLink.parent_id == parent_id, ParentStudentLink.student_id == student_id)
    )
    if not link.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not authorized to view this student")


@router.get("/children")
async def my_children(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User, StudentProfile, ParentStudentLink.relationship_label)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .join(ParentStudentLink, ParentStudentLink.student_id == User.id)
        .where(ParentStudentLink.parent_id == current_user.id)
    )
    return [
        {
            "student_id": str(user.id),
            "full_name": user.full_name,
            "student_number": profile.student_number,
            "class_name": profile.class_name,
            "relationship": relationship_label,
        }
        for user, profile, relationship_label in result.all()
    ]


@router.get("/children/{student_id}/attendance")
async def child_attendance(student_id: UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    await _assert_is_my_child(current_user.id, student_id, db)

    result = await db.execute(
        select(AttendanceRecord, AttendanceSession.session_date, AttendanceSession.club_id)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .where(AttendanceRecord.student_id == student_id)
        .order_by(AttendanceSession.session_date.desc())
    )
    return [
        {
            "session_date": session_date.isoformat(),
            "club_id": str(club_id),
            "status": record.status.value,
            "note": record.note,
        }
        for record, session_date, club_id in result.all()
    ]


@router.get("/children/{student_id}/feedback")
async def child_feedback(student_id: UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    await _assert_is_my_child(current_user.id, student_id, db)

    result = await db.execute(
        select(Feedback, Submission.task_id)
        .join(Submission, Submission.id == Feedback.submission_id)
        .where(Submission.student_id == student_id)
        .order_by(Feedback.created_at.desc())
    )
    return [
        {"task_id": str(task_id), "comment": fb.comment, "points_awarded": fb.points_awarded}
        for fb, task_id in result.all()
    ]


@router.get("/children/{student_id}/pa_jsK", response_model=PajskBreakdown)
async def child_pajsk(student_id: UUID, current_user: CurrentUser, year: int = None, db: AsyncSession = Depends(get_db)):
    await _assert_is_my_child(current_user.id, student_id, db)
    year = year or date.today().year
    breakdown = await calculate_pa_jsK(student_id, year, db)
    return PajskBreakdown(**breakdown)


@router.get("/notifications", response_model=list[NotificationOut])
async def my_notifications(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Notification).where(Notification.user_id == current_user.id).order_by(Notification.created_at.desc())
    )
    return result.scalars().all()


@router.patch("/notifications/{notification_id}/read", response_model=Message)
async def mark_notification_read(notification_id: UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    notif = await db.get(Notification, notification_id)
    if not notif or notif.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.is_read = True
    await db.commit()
    return Message(detail="Marked as read")
