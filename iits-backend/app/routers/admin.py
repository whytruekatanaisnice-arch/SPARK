"""Admin-only: user management, bulk import, dashboard, PAJSK export, gamification."""
import csv
import io
import logging
import re
import secrets
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import demo_store
from app.database import get_db
from app.config import settings
from app.models.attendance import AttendanceRecord, AttendanceSession, AttendanceStatus
from app.models.achievement import Achievement
from app.models.club import Club, ClubMembership
from app.models.competition import InterClubCompetition
from app.models.notification import Notification
from app.models.task import Submission, Task
from app.models.user import CoachProfile, ParentStudentLink, StudentProfile, User, UserRole
from app.schemas.common import Message
from app.schemas.competition import CompetitionOut, CompetitionUpdate
from app.schemas.club import StudentClubInvite
from app.schemas.report import (
    DashboardStats,
    LeaderboardEntry,
    MonthlyCategoryLeaderboard,
    MonthlyClubLeaderboardEntry,
    MonthlyGamificationLeaderboard,
)
from app.schemas.attendance import FaceEnrollmentRequest
from app.schemas.user import BulkImportResult, UserCreate, UserListItem, UserUpdate
from app.security import CurrentUser, hash_password, require_admin
from app.utils.email import send_password_reset_email, send_welcome_email
from app.utils.pagination import paginate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


async def _face_service_request(path: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    if not settings.PAJSK_FACE_SERVICE_URL or not settings.PAJSK_FACE_SERVICE_TOKEN:
        raise HTTPException(status_code=503, detail="Face recognition service is not configured")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.request(
                method,
                f"{settings.PAJSK_FACE_SERVICE_URL.rstrip('/')}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {settings.PAJSK_FACE_SERVICE_TOKEN}"},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Face recognition service timed out") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Face recognition service is unavailable") from exc
    if response.status_code in (401, 403):
        raise HTTPException(status_code=503, detail="Face recognition service token is not configured correctly")
    if response.status_code >= 500:
        raise HTTPException(status_code=503, detail="Face recognition service failed")
    if response.status_code != 200:
        if response.status_code in (400, 422):
            try:
                detail = response.json().get("message", "Face enrollment was rejected")
            except ValueError:
                detail = "Face enrollment was rejected"
            raise HTTPException(status_code=response.status_code, detail=detail)
        raise HTTPException(status_code=502, detail="Face recognition service rejected the request")
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Face recognition service returned an invalid response") from exc
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Face recognition service returned an invalid response")
    return result


# ---------------- User management ----------------

@router.get("/users", response_model=list[UserListItem])
async def list_users(role: str | None = None, q: str | None = None, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        users = [demo_store.public_user(user) for user in demo_store.collection("users")]
        if role:
            users = [user for user in users if user["role"] == role]
        if q:
            query = q.casefold()
            users = [
                user for user in users
                if query in user["full_name"].casefold() or query in user["email"].casefold()
            ]
        return sorted(users, key=lambda user: user["full_name"])

    stmt = select(User, StudentProfile, CoachProfile).outerjoin(
        StudentProfile, StudentProfile.user_id == User.id
    ).outerjoin(CoachProfile, CoachProfile.user_id == User.id)
    if role:
        stmt = stmt.where(User.role == role)
    if q:
        stmt = stmt.where(User.full_name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))
    result = await db.execute(stmt.order_by(User.full_name))
    return [
        UserListItem.model_validate({
            **UserListItem.model_validate(user).model_dump(),
            "student_number": student_profile.student_number if student_profile else None,
            "class_name": student_profile.class_name if student_profile else None,
            "ic_number": student_profile.ic_number if student_profile else None,
            "staff_number": coach_profile.staff_number if coach_profile else None,
            "subject": coach_profile.subject if coach_profile else None,
        })
        for user, student_profile, coach_profile in result.all()
    ]


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
    result = await db.execute(
        select(User, StudentProfile, CoachProfile)
        .outerjoin(StudentProfile, StudentProfile.user_id == User.id)
        .outerjoin(CoachProfile, CoachProfile.user_id == User.id)
        .where(User.id == user_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    user, student_profile, coach_profile = row
    return UserListItem.model_validate({
        **UserListItem.model_validate(user).model_dump(),
        "student_number": student_profile.student_number if student_profile else None,
        "class_name": student_profile.class_name if student_profile else None,
        "ic_number": student_profile.ic_number if student_profile else None,
        "staff_number": coach_profile.staff_number if coach_profile else None,
        "subject": coach_profile.subject if coach_profile else None,
    })


@router.patch("/users/{user_id}", response_model=UserListItem)
async def update_user(user_id: uuid.UUID, payload: UserUpdate, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    data = payload.model_dump(exclude_unset=True)
    if "email" in data and data["email"] != user.email:
        existing = await db.execute(select(User.id).where(User.email == data["email"], User.id != user_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already in use")

    profile_fields = {
        "student_number": "student_number",
        "class_name": "class_name",
        "ic_number": "ic_number",
    }
    coach_fields = {"staff_number": "staff_number", "subject": "subject"}
    profile_data = {field: data.pop(field) for field in profile_fields if field in data}
    coach_data = {field: data.pop(field) for field in coach_fields if field in data}
    for field, value in data.items():
        setattr(user, field, value)

    if profile_data and user.role == UserRole.STUDENT:
        profile_result = await db.execute(select(StudentProfile).where(StudentProfile.user_id == user.id))
        profile = profile_result.scalar_one_or_none()
        if profile is None:
            raise HTTPException(status_code=409, detail="Student profile is missing")
        if "student_number" in profile_data:
            if profile_data["student_number"] is None:
                raise HTTPException(status_code=422, detail="Student number cannot be blank")
            existing = await db.execute(
                select(StudentProfile.user_id).where(
                    StudentProfile.student_number == profile_data["student_number"],
                    StudentProfile.user_id != user.id,
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Student number already in use")
        for field, value in profile_data.items():
            setattr(profile, field, value)

    if coach_data and user.role == UserRole.COACH:
        coach_result = await db.execute(select(CoachProfile).where(CoachProfile.user_id == user.id))
        coach_profile = coach_result.scalar_one_or_none()
        if coach_profile is None:
            raise HTTPException(status_code=409, detail="Coach profile is missing")
        for field, value in coach_data.items():
            setattr(coach_profile, field, value)

    await db.commit()
    return await get_user(user_id, db)


@router.post("/clubs/{club_id}/invite", response_model=Message, status_code=status.HTTP_201_CREATED)
async def invite_student_to_club(
    club_id: uuid.UUID,
    payload: StudentClubInvite,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    club = await db.get(Club, club_id)
    if club is None or not club.is_active:
        raise HTTPException(status_code=404, detail="Active club not found")

    student_result = await db.execute(
        select(User)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .where(User.id == payload.student_id, User.role == UserRole.STUDENT, User.is_active.is_(True))
    )
    student = student_result.scalar_one_or_none()
    if student is None:
        raise HTTPException(status_code=404, detail="Active student not found")

    membership_result = await db.execute(
        select(ClubMembership).where(
            ClubMembership.club_id == club.id,
            ClubMembership.student_id == student.id,
        )
    )
    membership = membership_result.scalar_one_or_none()
    if membership and membership.is_active:
        raise HTTPException(status_code=409, detail="Student is already a member of this club")
    if membership:
        membership.is_active = True
    else:
        db.add(ClubMembership(club_id=club.id, student_id=student.id, is_active=True))

    db.add(Notification(
        user_id=student.id,
        title=f"Added to {club.name}",
        body=f"An administrator added you to {club.name}. Open My Clubs to view the club and its schedule.",
        created_by=current_user.id,
    ))
    await db.commit()
    return Message(detail=f"{student.full_name} was added to {club.name} and notified.")


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


@router.get("/face-enrollments")
async def list_face_enrollments(db: AsyncSession = Depends(get_db)):
    """List active student accounts and whether an enrollment photo exists for the IC."""
    service_result = await _face_service_request("/internal/students")
    face_students = service_result.get("students")
    if not isinstance(face_students, list):
        raise HTTPException(status_code=502, detail="Face recognition service returned an invalid student list")
    enrolled_ics = {
        re.sub(r"\D", "", item["ic"])
        for item in face_students
        if isinstance(item, dict) and isinstance(item.get("ic"), str)
    }
    result = await db.execute(
        select(User.id, User.full_name, StudentProfile.student_number, StudentProfile.ic_number)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .where(User.role == UserRole.STUDENT, User.is_active == True)  # noqa: E712
        .order_by(User.full_name)
    )
    return [
        {
            "user_id": str(user_id),
            "full_name": full_name,
            "student_number": student_number,
            "ic_number": ic_number,
            "face_enrolled": bool(ic_number and re.sub(r"\D", "", ic_number) in enrolled_ics),
        }
        for user_id, full_name, student_number, ic_number in result.all()
    ]


@router.post("/users/{user_id}/face")
async def enroll_student_face(
    user_id: uuid.UUID,
    payload: FaceEnrollmentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Enroll or replace a student's face photo; this route is admin-only."""
    student = await db.get(User, user_id)
    if not student or student.role != UserRole.STUDENT:
        raise HTTPException(status_code=404, detail="Student not found")
    profile_result = await db.execute(
        select(StudentProfile).where(StudentProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")

    ic_number = re.sub(r"\D", "", payload.ic_number)
    if not re.fullmatch(r"\d{12}", ic_number):
        raise HTTPException(status_code=400, detail="Student IC number must contain exactly 12 digits")
    all_profiles = await db.execute(
        select(StudentProfile.user_id, StudentProfile.ic_number).where(StudentProfile.ic_number.is_not(None))
    )
    for existing_user_id, existing_ic in all_profiles.all():
        if existing_user_id != user_id and re.sub(r"\D", "", existing_ic or "") == ic_number:
            raise HTTPException(status_code=409, detail="This IC number is already assigned to another student")

    enrollment = await _face_service_request(
        "/internal/enroll",
        method="POST",
        payload={"ic": ic_number, "name": student.full_name, "image": payload.image},
    )
    if enrollment.get("status") != "ok":
        raise HTTPException(status_code=502, detail="Face recognition service did not confirm enrollment")
    profile.ic_number = ic_number
    await db.commit()
    return {"detail": "Student face enrolled", "user_id": str(student.id), "ic_number": ic_number}


# ---------------- Dashboard ----------------

@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        users = demo_store.collection("users")
        clubs = demo_store.collection("clubs")
        tasks = demo_store.collection("tasks")
        submitted_task_ids = {
            submission["task_id"] for submission in demo_store.collection("submissions")
        }
        return DashboardStats(
            total_students=sum(user["role"] == UserRole.STUDENT.value for user in users),
            total_coaches=sum(user["role"] == UserRole.COACH.value for user in users),
            total_clubs=sum(club.get("is_active", True) for club in clubs),
            attendance_today=0,
            pending_tasks=sum(task["id"] not in submitted_task_ids for task in tasks),
        )

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

_GAMIFICATION_TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")
_GAMIFICATION_CATEGORIES = (
    ("Uniform Body", "uniform body"),
    ("Club & Society", "club & society"),
    ("Sports & Games", "sports & games"),
)


def _gamification_category_key(category: str | None) -> str:
    normalized = " ".join((category or "").casefold().split())
    aliases = {
        "club and society": "club & society",
        "sports": "sports & games",
        "sports and games": "sports & games",
    }
    return aliases.get(normalized, normalized)


@router.get("/monthly-gamification", response_model=MonthlyGamificationLeaderboard)
async def monthly_gamification_leaderboard(
    month: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    month_value = month or datetime.now(_GAMIFICATION_TIMEZONE).strftime("%Y-%m")
    try:
        start_date = date.fromisoformat(f"{month_value}-01")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Month must use YYYY-MM format") from exc
    if start_date.strftime("%Y-%m") != month_value:
        raise HTTPException(status_code=422, detail="Month must use YYYY-MM format")

    if start_date.month == 12:
        next_month = date(start_date.year + 1, 1, 1)
    else:
        next_month = date(start_date.year, start_date.month + 1, 1)
    start_datetime = datetime.combine(start_date, time.min, tzinfo=_GAMIFICATION_TIMEZONE)
    end_datetime = datetime.combine(next_month, time.min, tzinfo=_GAMIFICATION_TIMEZONE)
    end_date = next_month - timedelta(days=1)

    clubs = (
        await db.execute(select(Club).where(Club.is_active.is_(True)))
    ).scalars().all()
    club_ids = [club.id for club in clubs]
    scores = {
        club.id: {"attendance": 0, "tasks": 0, "achievements": 0}
        for club in clubs
    }

    if club_ids:
        attendance_rows = await db.execute(
            select(AttendanceSession.club_id, func.count(AttendanceRecord.id))
            .join(AttendanceRecord, AttendanceRecord.session_id == AttendanceSession.id)
            .where(
                AttendanceSession.club_id.in_(club_ids),
                AttendanceSession.session_date.between(start_date, end_date),
                AttendanceRecord.status == AttendanceStatus.PRESENT,
            )
            .group_by(AttendanceSession.club_id)
        )
        for club_id, count in attendance_rows.all():
            scores[club_id]["attendance"] = count

        task_rows = await db.execute(
            select(Task.club_id, func.count(func.distinct(Submission.id)))
            .join(Submission, Submission.task_id == Task.id)
            .where(
                Task.club_id.in_(club_ids),
                Submission.submitted_at >= start_datetime,
                Submission.submitted_at < end_datetime,
            )
            .group_by(Task.club_id)
        )
        for club_id, count in task_rows.all():
            scores[club_id]["tasks"] = count

        achievement_rows = await db.execute(
            select(Achievement.club_id, func.count(Achievement.id))
            .where(
                Achievement.club_id.in_(club_ids),
                or_(
                    Achievement.event_date.between(start_date, end_date),
                    and_(
                        Achievement.event_date.is_(None),
                        Achievement.created_at >= start_datetime,
                        Achievement.created_at < end_datetime,
                    ),
                ),
            )
            .group_by(Achievement.club_id)
        )
        for club_id, count in achievement_rows.all():
            scores[club_id]["achievements"] = count

    category_results = []
    for category, category_key in _GAMIFICATION_CATEGORIES:
        entries = []
        for club in clubs:
            if _gamification_category_key(club.category) != category_key:
                continue
            attendance_score = scores[club.id]["attendance"]
            task_score = scores[club.id]["tasks"]
            achievement_score = scores[club.id]["achievements"]
            entries.append(MonthlyClubLeaderboardEntry(
                club_id=club.id,
                club_name=club.name,
                category=category,
                attendance_score=float(attendance_score),
                task_score=float(task_score),
                achievement_score=float(achievement_score),
                total_score=float(attendance_score + task_score + achievement_score * 2),
                rank=0,
            ))
        entries.sort(key=lambda entry: (-entry.total_score, entry.club_name.casefold()))
        category_results.append(MonthlyCategoryLeaderboard(
            category=category,
            top_clubs=[entry.model_copy(update={"rank": rank}) for rank, entry in enumerate(entries[:3], start=1)],
        ))

    return MonthlyGamificationLeaderboard(
        month=start_date.strftime("%Y-%m"),
        categories=category_results,
    )


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
