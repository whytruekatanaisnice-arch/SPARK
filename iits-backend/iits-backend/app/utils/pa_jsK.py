"""
PAJSK (Penilaian Aktiviti Jasmani, Sukan dan Kokurikulum) auto-scoring.

All point weightings are read from `pajsk_config` (per category/key/year) so
admins can retune values every year without a code change or redeploy.

Call `recalculate_and_store` after ANY of these events so the student's
`student_profiles.pajsk_points` stays in sync automatically:
  - attendance marked
  - AJK role assigned / removed
  - achievement recorded
  - NILAM book logged
"""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.achievement import Achievement, AchievementRank
from app.models.attendance import AttendanceRecord, AttendanceStatus
from app.models.nilam import NilamRecord
from app.models.pajsk import PajskConfig
from app.models.role import RoleType, StudentRole
from app.models.user import StudentProfile


async def _get_config_points(db: AsyncSession, category: str, key: str, year: int, default: int = 0) -> int:
    result = await db.execute(
        select(PajskConfig.points).where(
            PajskConfig.category == category,
            PajskConfig.key == key,
            PajskConfig.year == year,
        )
    )
    points = result.scalar_one_or_none()
    return points if points is not None else default


async def calculate_pa_jsK(student_id: UUID, year: int, db: AsyncSession) -> dict:
    """
    Returns:
      {
        "role_points": int,          # sum of role_types.pajsk_points for student_roles in `year`
        "achievement_points": int,   # sum of achievement_ranks.pajsk_points for achievements in `year`
        "attendance_points": int,    # per-status count * config('attendance', status)
        "nilam_points": int,         # nilam_count * config('nilam', 'book_logged')
        "total": int
      }
    """
    # --- Role points ---
    role_points_result = await db.execute(
        select(func.coalesce(func.sum(RoleType.pajsk_points), 0))
        .select_from(StudentRole)
        .join(RoleType, RoleType.id == StudentRole.role_type_id)
        .where(StudentRole.student_id == student_id, StudentRole.year == year)
    )
    role_points = role_points_result.scalar_one()

    # --- Achievement points ---
    achievement_points_result = await db.execute(
        select(func.coalesce(func.sum(AchievementRank.pajsk_points), 0))
        .select_from(Achievement)
        .join(AchievementRank, AchievementRank.id == Achievement.rank_id)
        .where(
            Achievement.student_id == student_id,
            func.extract("year", Achievement.created_at) == year,
        )
    )
    achievement_points = achievement_points_result.scalar_one()

    # --- Attendance points (per status, since "present"/"late"/"excused" may carry different weight) ---
    from app.models.attendance import AttendanceSession  # local import to avoid circular import at module load

    attendance_points = 0
    for status in AttendanceStatus:
        count_result = await db.execute(
            select(func.count())
            .select_from(AttendanceRecord)
            .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
            .where(
                AttendanceRecord.student_id == student_id,
                AttendanceRecord.status == status,
                func.extract("year", AttendanceSession.session_date) == year,
            )
        )
        count = count_result.scalar_one()
        per_unit = await _get_config_points(db, "attendance", status.value, year, default=0)
        attendance_points += count * per_unit

    # --- NILAM points ---
    nilam_count_result = await db.execute(
        select(func.count())
        .select_from(NilamRecord)
        .where(
            NilamRecord.student_id == student_id,
            func.extract("year", NilamRecord.date_completed) == year,
        )
    )
    nilam_count = nilam_count_result.scalar_one()
    nilam_per_book = await _get_config_points(db, "nilam", "book_logged", year, default=0)
    nilam_points = nilam_count * nilam_per_book

    total = role_points + achievement_points + attendance_points + nilam_points

    return {
        "role_points": int(role_points),
        "achievement_points": int(achievement_points),
        "attendance_points": int(attendance_points),
        "nilam_points": int(nilam_points),
        "total": int(total),
    }


async def recalculate_and_store(student_id: UUID, year: int, db: AsyncSession) -> dict:
    """Recompute a student's PAJSK breakdown and persist the total onto their profile."""
    breakdown = await calculate_pa_jsK(student_id, year, db)

    result = await db.execute(select(StudentProfile).where(StudentProfile.user_id == student_id))
    profile = result.scalar_one_or_none()
    if profile is not None:
        profile.pajsk_points = breakdown["total"]
        await db.commit()

    return breakdown
