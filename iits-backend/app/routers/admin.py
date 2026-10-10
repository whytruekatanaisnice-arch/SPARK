"""Admin-only: user management, bulk import, dashboard, PAJSK export, gamification."""
import csv
import io
import logging
import secrets
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.attendance import AttendanceRecord, AttendanceSession, AttendanceStatus
from app.models.club import Club, ClubMembership
from app.models.competition import InterClubCompetition
from app.models.task import Submission, Task
from app.models.user import CoachProfile, ParentStudentLink, StudentProfile, User, UserRole
from app.schemas.common import Message
from app.schemas.competition import CompetitionOut, CompetitionUpdate
from app.schemas.report import DashboardStats, LeaderboardEntry
from app.schemas.user import BulkImportResult, UserCreate, UserListItem, UserUpdate
from app.security import CurrentUser, hash_password, require_admin
from app.utils.email import send_password_reset_email, send_welcome_email
from app.utils.pagination import paginate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ---------------- User management ----------------

@router.get("/users", response_model=list[UserListItem])
async def list_users(role: str | None = None, q: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if q:
        stmt = stmt.where(User.full_name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))
    result = await db.execute(stmt.order_by(User.full_name))
    return result.scalars().all()


@router.post("/users", response_model=UserListItem, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already in use")

    temp_password = payload.password or secrets.token_urlsafe(9)
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        role=UserRole(payload.role),
        phone=payload.phone,
        password_hash=hash_password(temp_password),
    )
    db.add(user)
    await db.flush()

    if user.role == UserRole.STUDENT:
        if not payload.student_number:
            raise HTTPException(status_code=400, detail="student_number is required for students")
        db.add(StudentProfile(
            user_id=user.id,
            student_number=payload.student_number,
            class_name=payload.class_name,
            ic_number=payload.ic_number,
        ))
    elif user.role == UserRole.COACH:
        db.add(CoachProfile(user_id=user.id, staff_number=payload.staff_number, subject=payload.subject))
    elif user.role == UserRole.PARENT and payload.child_student_numbers:
        for student_number in payload.child_student_numbers:
            child = await db.execute(select(StudentProfile).where(StudentProfile.student_number == student_number))
            child_profile = child.scalar_one_or_none()
            if child_profile:
                db.add(ParentStudentLink(parent_id=user.id, student_id=child_profile.user_id))

    await db.commit()
    await db.refresh(user)

    email_sent = await send_welcome_email(user.email, user.full_name, temp_password, user.role.value)
    if not email_sent:
        logger.warning("Welcome email failed to send to %s — temp password: %s", user.email, temp_password)

    return user


@router.get("/users/{user_id}", response_model=UserListItem)
async def get_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/users/{user_id}", response_model=UserListItem)
async def update_user(user_id: uuid.UUID, payload: UserUpdate, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    data = payload.model_dump(exclude_unset=True)
    class_name = data.pop("class_name", None)
    for field, value in data.items():
        setattr(user, field, value)

    if class_name is not None and user.role == UserRole.STUDENT:
        profile = await db.execute(select(StudentProfile).where(StudentProfile.user_id == user.id))
        profile = profile.scalar_one_or_none()
        if profile:
            profile.class_name = class_name

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}", response_model=Message)
async def deactivate_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    await db.commit()
    return Message(detail="User deactivated")


@router.post("/users/{user_id}/reset-password", response_model=Message)
async def reset_password(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    temp_password = secrets.token_urlsafe(9)
    user.password_hash = hash_password(temp_password)
    await db.commit()

    email_sent = await send_password_reset_email(user.email, user.full_name, temp_password)
    if email_sent:
        return Message(detail=f"Password reset. A new temporary password was emailed to {user.email}.")
    # SMTP failed (or isn't configured) — fall back to showing it so the admin isn't stuck.
    logger.warning("Password reset email failed to send to %s — temp password: %s", user.email, temp_password)
    return Message(detail=f"Password reset, but the email could not be sent. Temporary password: {temp_password}")


@router.post("/users/bulk-import", response_model=BulkImportResult)
async def bulk_import_students(file: UploadFile, db: AsyncSession = Depends(get_db)):
    """
    CSV columns expected: full_name,email,student_number,class_name,ic_number
    See sample_students.csv in the project root for a template.
    """
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    created, skipped, errors = 0, 0, []
    pending_emails: list[tuple[str, str, str]] = []

    for i, row in enumerate(reader, start=2):  # row 1 = header
        try:
            email = row["email"].strip()
            existing = await db.execute(select(User).where(User.email == email))
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            temp_password = secrets.token_urlsafe(9)
            user = User(
                email=email,
                full_name=row["full_name"].strip(),
                role=UserRole.STUDENT,
                password_hash=hash_password(temp_password),
            )
            db.add(user)
            await db.flush()
            db.add(StudentProfile(
                user_id=user.id,
                student_number=row["student_number"].strip(),
                class_name=row.get("class_name", "").strip() or None,
                ic_number=row.get("ic_number", "").strip() or None,
            ))
            created += 1
            pending_emails.append((email, row["full_name"].strip(), temp_password))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Row {i}: {exc}")

    await db.commit()

    for email, full_name, temp_password in pending_emails:
        email_sent = await send_welcome_email(email, full_name, temp_password, "student")
        if not email_sent:
            errors.append(f"{email}: account created but welcome email failed to send")

    return BulkImportResult(created=created, skipped=skipped, errors=errors)


# ---------------- Dashboard ----------------

@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(db: AsyncSession = Depends(get_db)):
    total_students = (await db.execute(select(func.count()).select_from(User).where(User.role == UserRole.STUDENT))).scalar_one()
    total_coaches = (await db.execute(select(func.count()).select_from(User).where(User.role == UserRole.COACH))).scalar_one()
    total_clubs = (await db.execute(select(func.count()).select_from(Club).where(Club.is_active == True))).scalar_one()  # noqa: E712

    today = date.today()
    attendance_today = (
        await db.execute(
            select(func.count())
            .select_from(AttendanceRecord)
            .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
            .where(AttendanceSession.session_date == today, AttendanceRecord.status == AttendanceStatus.PRESENT)
        )
    ).scalar_one()

    pending_tasks = (
        await db.execute(
            select(func.count(func.distinct(Task.id)))
            .select_from(Task)
            .outerjoin(Submission, Submission.task_id == Task.id)
            .where(Submission.id.is_(None))
        )
    ).scalar_one()

    return DashboardStats(
        total_students=total_students,
        total_coaches=total_coaches,
        total_clubs=total_clubs,
        attendance_today=attendance_today,
        pending_tasks=pending_tasks,
    )


# ---------------- Gamification ----------------

@router.get("/inter-club-competitions", response_model=list[CompetitionOut])
async def list_competitions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(InterClubCompetition).order_by(InterClubCompetition.start_date.desc()))
    return result.scalars().all()


@router.post("/inter-club-competitions", status_code=status.HTTP_201_CREATED, response_model=CompetitionOut)
async def create_competition(
    name: str, description: str | None, start_date: date, end_date: date,
    current_user: CurrentUser, db: AsyncSession = Depends(get_db),
):
    comp = InterClubCompetition(name=name, description=description, start_date=start_date, end_date=end_date, created_by=current_user.id)
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return comp


@router.patch("/inter-club-competitions/{competition_id}", response_model=CompetitionOut)
async def update_competition(competition_id: uuid.UUID, payload: CompetitionUpdate, db: AsyncSession = Depends(get_db)):
    comp = await db.get(InterClubCompetition, competition_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(comp, field, value)
    await db.commit()
    await db.refresh(comp)
    return comp


@router.delete("/inter-club-competitions/{competition_id}", response_model=Message)
async def delete_competition(competition_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    comp = await db.get(InterClubCompetition, competition_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found")
    await db.delete(comp)
    await db.commit()
    return Message(detail="Competition deleted")


@router.get("/inter-club-competitions/{competition_id}/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(competition_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    comp = await db.get(InterClubCompetition, competition_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found")

    clubs = (await db.execute(select(Club).where(Club.is_active == True))).scalars().all()  # noqa: E712

    entries = []
    for club in clubs:
        attendance_score = (
            await db.execute(
                select(func.count())
                .select_from(AttendanceRecord)
                .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
                .where(
                    AttendanceSession.club_id == club.id,
                    AttendanceRecord.status == AttendanceStatus.PRESENT,
                    AttendanceSession.session_date.between(comp.start_date, comp.end_date),
                )
            )
        ).scalar_one()

        task_score = (
            await db.execute(
                select(func.count(func.distinct(Submission.id)))
                .select_from(Submission)
                .join(Task, Task.id == Submission.task_id)
                .where(Task.club_id == club.id)
            )
        ).scalar_one()

        from app.models.achievement import Achievement
        achievement_score = (
            await db.execute(select(func.count()).select_from(Achievement).where(Achievement.club_id == club.id))
        ).scalar_one()

        total = attendance_score * 1.0 + task_score * 1.0 + achievement_score * 2.0
        entries.append(LeaderboardEntry(
            club_id=club.id, club_name=club.name,
            attendance_score=float(attendance_score), task_score=float(task_score),
            achievement_score=float(achievement_score), total_score=total, rank=0,
        ))

    entries.sort(key=lambda e: e.total_score, reverse=True)
    for i, entry in enumerate(entries, start=1):
        entry.rank = i

    return entries
