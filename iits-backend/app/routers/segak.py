"""Coach bulk-entry and reporting API for SEGAK assessments."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.club import Club, ClubMembership
from app.models.segak import SegakAssessment
from app.models.user import StudentProfile, User, UserRole
from app.schemas.segak import SegakBulkSave, SegakBulkSaveOut, SegakRecordOut
from app.security import CurrentUser, require_coach

router = APIRouter(
    prefix="/api/coach/segak",
    tags=["coach:segak"],
    dependencies=[Depends(require_coach)],
)


async def _authorized_roster(
    club_id: UUID,
    current_user: User,
    db: AsyncSession,
) -> list[tuple]:
    club = await db.get(Club, club_id)
    if club is None or not club.is_active:
        raise HTTPException(status_code=404, detail="Club not found")
    if current_user.role != UserRole.ADMIN and club.coach_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only enter SEGAK results for your assigned clubs")

    result = await db.execute(
        select(User.id, User.full_name, StudentProfile.student_number, StudentProfile.class_name)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .join(
            ClubMembership,
            and_(
                ClubMembership.student_id == User.id,
                ClubMembership.club_id == club_id,
                ClubMembership.is_active.is_(True),
            ),
        )
        .where(User.role == UserRole.STUDENT, User.is_active.is_(True))
        .distinct()
        .order_by(StudentProfile.class_name, User.full_name)
    )
    return result.all()


def _calculate_bmi(weight_kg: Decimal | None, height_cm: Decimal | None) -> Decimal | None:
    if weight_kg is None or height_cm is None:
        return None
    height_m = height_cm / Decimal("100")
    return (weight_kg / (height_m * height_m)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@router.get("", response_model=list[SegakRecordOut])
async def get_segak_roster(
    club_id: UUID,
    assessment_date: date,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    if assessment_date > date.today():
        raise HTTPException(status_code=422, detail="Assessment date cannot be in the future")
    roster = await _authorized_roster(club_id, current_user, db)
    records_result = await db.execute(
        select(SegakAssessment).where(
            SegakAssessment.assessment_date == assessment_date,
            SegakAssessment.student_id.in_([student[0] for student in roster]),
        )
    ) if roster else None
    records = {
        record.student_id: record
        for record in records_result.scalars().all()
    } if records_result else {}

    return [
        SegakRecordOut(
            student_id=student_id,
            full_name=full_name,
            student_number=student_number,
            class_name=class_name,
            weight_kg=(record.weight_kg if record else None),
            height_cm=(record.height_cm if record else None),
            bmi=(record.bmi if record else None),
            step_test_recovery_bpm=(record.step_test_recovery_bpm if record else None),
            push_up_type=(record.push_up_type if record else None),
            push_up_reps=(record.push_up_reps if record else None),
            curl_up_reps=(record.curl_up_reps if record else None),
            sit_and_reach_cm=(record.sit_and_reach_cm if record else None),
        )
        for student_id, full_name, student_number, class_name in roster
    ]


@router.put("/bulk", response_model=SegakBulkSaveOut)
async def save_segak_bulk(
    payload: SegakBulkSave,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    if payload.assessment_date > date.today():
        raise HTTPException(status_code=422, detail="Assessment date cannot be in the future")
    roster = await _authorized_roster(payload.club_id, current_user, db)
    roster_ids = {student_id for student_id, *_ in roster}
    submitted_ids = {record.student_id for record in payload.records}
    if not submitted_ids.issubset(roster_ids):
        raise HTTPException(status_code=403, detail="One or more students are outside this club's roster")

    records_to_process = [
        record for record in payload.records if record.has_measurements() or record.clear_record
    ]
    if not records_to_process:
        raise HTTPException(status_code=422, detail="Enter at least one SEGAK value before saving")

    changed_count = 0
    for record in records_to_process:
        result = await db.execute(
            select(SegakAssessment).where(
                SegakAssessment.student_id == record.student_id,
                SegakAssessment.assessment_date == payload.assessment_date,
            )
        )
        existing = result.scalar_one_or_none()
        if record.clear_record:
            if existing is not None:
                await db.delete(existing)
                changed_count += 1
            continue
        if existing is None:
            existing = SegakAssessment(
                student_id=record.student_id,
                assessed_by=current_user.id,
                assessment_date=payload.assessment_date,
            )
            db.add(existing)

        for field in (
            "weight_kg",
            "height_cm",
            "step_test_recovery_bpm",
            "push_up_type",
            "push_up_reps",
            "curl_up_reps",
            "sit_and_reach_cm",
        ):
            value = getattr(record, field)
            setattr(existing, field, value)
        existing.bmi = _calculate_bmi(existing.weight_kg, existing.height_cm)
        existing.assessed_by = current_user.id
        changed_count += 1

    await db.commit()
    return SegakBulkSaveOut(
        detail="SEGAK records saved",
        saved_count=changed_count,
        assessment_date=payload.assessment_date,
    )
