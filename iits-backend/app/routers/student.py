"""Student self-service: my clubs, schedule, role, profile, PAJSK, achievements."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import demo_store
from app.database import get_db
from app.models.achievement import Achievement
from app.models.club import Club, ClubMembership, ClubSchedule
from app.models.role import RoleType, StudentRole
from app.models.user import StudentProfile, User
from app.schemas.achievement import AchievementOut
from app.schemas.auth import UserOut
from app.schemas.club import ClubOut
from app.schemas.report import PajskBreakdown
from app.schemas.role import StudentRoleOut
from app.schemas.user import UserUpdate
from app.security import CurrentUser, require_student
from app.utils.pa_jsK import calculate_pa_jsK

router = APIRouter(prefix="/api/student", tags=["student"], dependencies=[Depends(require_student)])


@router.get("/clubs", response_model=list[ClubOut])
async def my_clubs(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        club_ids = {
            membership["club_id"]
            for membership in demo_store.collection("memberships")
            if membership["student_id"] == str(current_user.id) and membership.get("is_active", True)
        }
        return [
            club for club in demo_store.collection("clubs")
            if club["id"] in club_ids and club.get("is_active", True)
        ]
    result = await db.execute(
        select(Club)
        .join(ClubMembership, ClubMembership.club_id == Club.id)
        .where(ClubMembership.student_id == current_user.id, ClubMembership.is_active == True)  # noqa: E712
    )
    return result.scalars().all()


@router.get("/schedule")
async def my_schedule(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        club_ids = {
            membership["club_id"]
            for membership in demo_store.collection("memberships")
            if membership["student_id"] == str(current_user.id) and membership.get("is_active", True)
        }
        clubs = [club for club in demo_store.collection("clubs") if club["id"] in club_ids]
        return [
            {
                "club_name": club["name"],
                "club_id": club["id"],
                **schedule,
            }
            for club in clubs
            for schedule in club.get("schedules", [])
        ]
    result = await db.execute(
        select(ClubSchedule, Club.name)
        .join(Club, Club.id == ClubSchedule.club_id)
        .join(ClubMembership, ClubMembership.club_id == Club.id)
        .where(ClubMembership.student_id == current_user.id, ClubMembership.is_active == True)  # noqa: E712
    )
    return [
        {
            "club_name": club_name,
            "club_id": str(schedule.club_id),
            "day_of_week": schedule.day_of_week.value,
            "start_time": schedule.start_time.isoformat(),
            "end_time": schedule.end_time.isoformat(),
        }
        for schedule, club_name in result.all()
    ]


@router.get("/role", response_model=list[StudentRoleOut])
async def my_roles(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        return []
    result = await db.execute(select(StudentRole).where(StudentRole.student_id == current_user.id))
    return result.scalars().all()


@router.get("/pa_jsK", response_model=PajskBreakdown)
async def my_pajsk(current_user: CurrentUser, year: int = None, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        user = demo_store.find_user(str(current_user.id))
        total = user.get("pajsk_points", 78) if user else 0
        role_points, achievement_points, attendance_points = 25, 20, 23
        return PajskBreakdown(
            role_points=role_points,
            achievement_points=achievement_points,
            attendance_points=attendance_points,
            nilam_points=max(0, total - role_points - achievement_points - attendance_points),
            total=total,
        )
    year = year or date.today().year
    breakdown = await calculate_pa_jsK(current_user.id, year, db)
    return PajskBreakdown(**breakdown)


@router.get("/achievements", response_model=list[AchievementOut])
async def my_achievements(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        return []
    result = await db.execute(select(Achievement).where(Achievement.student_id == current_user.id))
    return result.scalars().all()


@router.patch("/profile", response_model=UserOut)
async def update_profile(payload: UserUpdate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    class_name = data.pop("class_name", None)
    data.pop("is_active", None)  # students may not deactivate themselves
    if demo_store.is_enabled():
        if class_name is not None:
            data["class_name"] = class_name
        updated = demo_store.update_user(str(current_user.id), data)
        if updated is None:
            raise HTTPException(status_code=404, detail="User not found")
        return UserOut.model_validate(updated)

    for field, value in data.items():
        setattr(current_user, field, value)

    if class_name is not None:
        profile_result = await db.execute(select(StudentProfile).where(StudentProfile.user_id == current_user.id))
        profile = profile_result.scalar_one_or_none()
        if profile:
            profile.class_name = class_name

    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/profile")
async def my_profile(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        user = demo_store.find_user(str(current_user.id))
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "id": user["id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "phone": user.get("phone"),
            "student_number": user.get("student_number"),
            "class_name": user.get("class_name"),
        }
    profile = (await db.execute(select(StudentProfile).where(StudentProfile.user_id == current_user.id))).scalar_one_or_none()
    return {
        "id": str(current_user.id),
        "full_name": current_user.full_name,
        "email": current_user.email,
        "phone": current_user.phone,
        "student_number": profile.student_number if profile else None,
        "class_name": profile.class_name if profile else None,
    }
