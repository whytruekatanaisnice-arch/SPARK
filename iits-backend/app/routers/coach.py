"""Coach: AJK role assignment, progress notes, achievements, notification broadcast."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.achievement import Achievement, AchievementRank
from app.models.club import ClubMembership
from app.models.notification import Notification
from app.models.user import StudentProfile, User
from app.models.progress import ProgressNote
from app.models.role import RoleType, StudentRole
from app.models.user import ParentStudentLink
from app.schemas.achievement import AchievementCreate, AchievementOut, AchievementRankOut
from app.schemas.common import Message
from app.schemas.notification import NotificationBroadcast
from app.schemas.progress import ProgressCreate, ProgressOut
from app.schemas.role import AssignRoleRequest, RoleTypeOut, StudentRoleOut
from app.security import CurrentUser, require_coach
from app.utils.pa_jsK import recalculate_and_store

router = APIRouter(prefix="/api/coach", tags=["coach"], dependencies=[Depends(require_coach)])


# ---------------- Club roster (needed for attendance, roles, achievements) ----------------

@router.get("/clubs/{club_id}/roster")
async def club_roster(club_id: UUID, db: AsyncSession = Depends(get_db)):
    """Active members of a club, for attendance checklists / QR lookup / role & achievement pickers."""
    result = await db.execute(
        select(User.id, User.full_name, StudentProfile.student_number, StudentProfile.class_name)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .join(ClubMembership, ClubMembership.student_id == User.id)
        .where(ClubMembership.club_id == club_id, ClubMembership.is_active == True)  # noqa: E712
        .order_by(User.full_name)
    )
    return [
        {"id": str(sid), "full_name": full_name, "student_number": student_number, "class_name": class_name}
        for sid, full_name, student_number, class_name in result.all()
    ]


# ---------------- AJK Role assignment ----------------

@router.get("/role-types", response_model=list[RoleTypeOut])
async def list_role_types(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RoleType))
    return result.scalars().all()


@router.post("/roles/assign", response_model=StudentRoleOut, status_code=status.HTTP_201_CREATED)
async def assign_role(payload: AssignRoleRequest, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(StudentRole).where(
            StudentRole.club_id == payload.club_id,
            StudentRole.student_id == payload.student_id,
            StudentRole.year == payload.year,
        )
    )
    role = existing.scalar_one_or_none()
    if role:
        role.role_type_id = payload.role_type_id
    else:
        role = StudentRole(**payload.model_dump(), assigned_by=current_user.id)
        db.add(role)

    await db.commit()
    await db.refresh(role)

    # Auto-save to the student profile for PAJSK scoring — no manual sync step.
    await recalculate_and_store(payload.student_id, payload.year, db)

    return role


@router.get("/roles", response_model=list[StudentRoleOut])
async def list_roles(club_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(StudentRole).where(StudentRole.club_id == club_id))
    return result.scalars().all()


@router.delete("/roles/{role_id}", response_model=Message)
async def remove_role(role_id: UUID, db: AsyncSession = Depends(get_db)):
    role = await db.get(StudentRole, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role assignment not found")
    student_id, year = role.student_id, role.year
    await db.delete(role)
    await db.commit()
    await recalculate_and_store(student_id, year, db)
    return Message(detail="Role removed")


# ---------------- Progress notes ----------------

@router.post("/progress", response_model=ProgressOut, status_code=status.HTTP_201_CREATED)
async def log_progress(payload: ProgressCreate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    note = ProgressNote(**payload.model_dump(), coach_id=current_user.id)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


@router.get("/students/{student_id}/progress", response_model=list[ProgressOut])
async def get_progress(student_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ProgressNote).where(ProgressNote.student_id == student_id).order_by(ProgressNote.created_at.desc())
    )
    return result.scalars().all()


# ---------------- Achievements ----------------

@router.get("/achievement-ranks", response_model=list[AchievementRankOut])
async def list_achievement_ranks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AchievementRank))
    return result.scalars().all()


@router.post("/achievements", response_model=AchievementOut, status_code=status.HTTP_201_CREATED)
async def record_achievement(payload: AchievementCreate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    achievement = Achievement(**payload.model_dump(), recorded_by=current_user.id)
    db.add(achievement)
    await db.commit()
    await db.refresh(achievement)

    # Auto-calculate points immediately, reflected on the student dashboard right away.
    year = achievement.event_date.year if achievement.event_date else achievement.created_at.year
    await recalculate_and_store(payload.student_id, year, db)

    return achievement


@router.get("/achievements", response_model=list[AchievementOut])
async def list_achievements(club_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Achievement).where(Achievement.club_id == club_id))
    return result.scalars().all()


# ---------------- Notifications broadcast ----------------

@router.post("/notifications/broadcast", response_model=Message)
async def broadcast_notification(payload: NotificationBroadcast, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    target_user_ids: set[UUID] = set(payload.user_ids or [])

    if payload.club_id:
        members = await db.execute(
            select(ClubMembership.student_id).where(ClubMembership.club_id == payload.club_id, ClubMembership.is_active == True)  # noqa: E712
        )
        student_ids = [row[0] for row in members.all()]

        if payload.audience in ("students", "both"):
            target_user_ids.update(student_ids)

        if payload.audience in ("parents", "both"):
            for sid in student_ids:
                parents = await db.execute(select(ParentStudentLink.parent_id).where(ParentStudentLink.student_id == sid))
                target_user_ids.update(row[0] for row in parents.all())

    if not target_user_ids:
        raise HTTPException(status_code=400, detail="No recipients resolved — provide club_id and/or user_ids")

    for uid in target_user_ids:
        db.add(Notification(user_id=uid, title=payload.title, body=payload.body, created_by=current_user.id))

    await db.commit()
    return Message(detail=f"Notification sent to {len(target_user_ids)} recipient(s)")
