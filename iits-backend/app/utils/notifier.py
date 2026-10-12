"""
Event notifications: each helper creates an in-app Notification row AND sends
an email, so users see it in the portal and in their inbox.

Email failures never raise (see utils/email.py) — the in-app notification is
the source of truth and is always written.
"""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import ParentStudentLink, User, UserRole
from app.utils.email import (
    absence_email_body, certificate_decision_email_body,
    certificate_submitted_email_body, send_email,
)

logger = logging.getLogger(__name__)


async def _notify(db: AsyncSession, user: User, title: str, body: str, email_subject: str, email_body: str,
                  created_by: UUID | None = None) -> None:
    db.add(Notification(user_id=user.id, title=title, body=body, created_by=created_by))
    await send_email(user.email, email_subject, email_body)


async def _guardians_of(db: AsyncSession, student_id: UUID) -> list[User]:
    result = await db.execute(
        select(User)
        .join(ParentStudentLink, ParentStudentLink.parent_id == User.id)
        .where(ParentStudentLink.student_id == student_id, User.is_active == True)  # noqa: E712
    )
    return list(result.scalars().all())


async def notify_absence(db: AsyncSession, student: User, club_name: str, session_date: str,
                         created_by: UUID | None = None) -> None:
    """Student marked ABSENT -> notify the student and every linked parent."""
    title = f"Absent from {club_name}"
    body = f"{student.full_name} was marked absent from {club_name} on {session_date}. A certificate can be uploaded if there was a valid reason."

    await _notify(db, student, title, body,
                  f"Absence notice: {club_name} on {session_date}",
                  absence_email_body(student.full_name, student.full_name, club_name, session_date, True), created_by)

    for parent in await _guardians_of(db, student.id):
        await _notify(db, parent, title, body,
                      f"Absence notice: {student.full_name} — {club_name} on {session_date}",
                      absence_email_body(parent.full_name, student.full_name, club_name, session_date, False), created_by)
    await db.commit()


async def notify_admins_new_certificate(db: AsyncSession, student: User, club_name: str, reason: str,
                                        created_by: UUID | None = None) -> None:
    """Certificate submitted -> notify every active admin to review it."""
    admins = (await db.execute(select(User).where(User.role == UserRole.ADMIN, User.is_active == True))).scalars().all()  # noqa: E712
    for admin in admins:
        await _notify(db, admin, f"Certificate awaiting review: {student.full_name}",
                      f"{student.full_name} submitted a certificate ({club_name}). Reason: {reason}",
                      f"Certificate to review: {student.full_name}",
                      certificate_submitted_email_body(admin.full_name, student.full_name, club_name, reason), created_by)
    await db.commit()


async def notify_certificate_decision(db: AsyncSession, student: User, approved: bool, review_note: str | None,
                                      created_by: UUID | None = None) -> None:
    """Admin decided -> notify the student and linked parents."""
    word = "approved" if approved else "rejected"
    title = f"Certificate {word}"
    body = f"{student.full_name}'s certificate was {word}." + (f" Note: {review_note}" if review_note else "")

    await _notify(db, student, title, body, f"Your certificate was {word}",
                  certificate_decision_email_body(student.full_name, student.full_name, approved, review_note, True), created_by)
    for parent in await _guardians_of(db, student.id):
        await _notify(db, parent, title, body, f"{student.full_name}'s certificate was {word}",
                      certificate_decision_email_body(parent.full_name, student.full_name, approved, review_note, False), created_by)
    await db.commit()
