"""Coach-facing attendance: create session, bulk-mark, list sessions."""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.attendance import AttendanceRecord, AttendanceSession, AttendanceStatus
from app.schemas.attendance import (
    AttendanceSessionOut, BulkMarkRequest, CreateSessionRequest,
)
from app.security import CurrentUser, require_coach
from app.utils.pa_jsK import recalculate_and_store

router = APIRouter(prefix="/api/coach/attendance", tags=["coach:attendance"], dependencies=[Depends(require_coach)])


@router.post("/sessions", response_model=AttendanceSessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(payload: CreateSessionRequest, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    session = AttendanceSession(club_id=payload.club_id, session_date=payload.session_date, created_by=current_user.id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/sessions/{session_id}/records", status_code=status.HTTP_200_OK)
async def bulk_mark(session_id: UUID, payload: BulkMarkRequest, db: AsyncSession = Depends(get_db)):
    """Mark (or update) attendance for many students at once, then recalculate PAJSK for each."""
    session = await db.get(AttendanceSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    year = session.session_date.year

    for mark in payload.records:
        existing = await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.session_id == session_id,
                AttendanceRecord.student_id == mark.student_id,
            )
        )
        record = existing.scalar_one_or_none()
        if record:
            record.status = AttendanceStatus(mark.status)
            record.note = mark.note
            record.marked_via = mark.marked_via
        else:
            db.add(AttendanceRecord(
                session_id=session_id, student_id=mark.student_id,
                status=AttendanceStatus(mark.status), note=mark.note, marked_via=mark.marked_via,
            ))

    await db.commit()

    # Recalculate PAJSK attendance points for every affected student (auto-sync, no manual step).
    for mark in payload.records:
        await recalculate_and_store(mark.student_id, year, db)

    return {"detail": f"{len(payload.records)} attendance records saved"}


@router.get("/sessions", response_model=list[AttendanceSessionOut])
async def list_sessions(club_id: UUID | None = None, session_date: date | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(AttendanceSession)
    if club_id:
        stmt = stmt.where(AttendanceSession.club_id == club_id)
    if session_date:
        stmt = stmt.where(AttendanceSession.session_date == session_date)
    result = await db.execute(stmt.order_by(AttendanceSession.session_date.desc()))
    return result.scalars().all()
