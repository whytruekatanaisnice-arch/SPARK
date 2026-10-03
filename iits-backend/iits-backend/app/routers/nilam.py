"""Student NILAM reading log — auto-syncs into PAJSK scoring, no separate portal."""
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.nilam import NilamRecord
from app.schemas.nilam import NilamCreate, NilamOut
from app.security import CurrentUser, require_student
from app.utils.pa_jsK import recalculate_and_store

router = APIRouter(prefix="/api/student/nilam", tags=["student:nilam"], dependencies=[Depends(require_student)])


@router.post("", response_model=NilamOut, status_code=status.HTTP_201_CREATED)
async def log_reading(payload: NilamCreate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    record = NilamRecord(**payload.model_dump(), student_id=current_user.id)
    db.add(record)
    await db.commit()
    await db.refresh(record)

    # Auto-sync into PAJSK immediately — this is the whole point of the feature.
    await recalculate_and_store(current_user.id, payload.date_completed.year, db)

    return record


@router.get("", response_model=list[NilamOut])
async def list_my_readings(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(NilamRecord).where(NilamRecord.student_id == current_user.id).order_by(NilamRecord.date_completed.desc())
    )
    return result.scalars().all()
