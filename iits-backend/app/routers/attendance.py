"""Coach-facing attendance: create session, bulk-mark, list sessions."""
from datetime import date
import re
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.attendance import AttendanceRecord, AttendanceSession, AttendanceStatus
from app.schemas.attendance import (
    AttendanceRecordOut, AttendanceSessionOut, BulkMarkRequest, CreateSessionRequest,
    FaceRecognitionRequest,
)
from app.models.club import Club, ClubMembership
from app.models.user import StudentProfile, User, UserRole
from app.security import CurrentUser, require_coach
from app.utils.notifier import notify_absence
from app.utils.pa_jsK import recalculate_and_store

router = APIRouter(prefix="/api/coach/attendance", tags=["coach:attendance"], dependencies=[Depends(require_coach)])


async def _get_accessible_club(club_id: UUID, current_user: CurrentUser, db: AsyncSession) -> Club:
    club = await db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    if current_user.role != UserRole.ADMIN and club.coach_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only manage attendance for your own clubs")
    return club


async def _get_accessible_session(session_id: UUID, current_user: CurrentUser, db: AsyncSession) -> AttendanceSession:
    session = await db.get(AttendanceSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await _get_accessible_club(session.club_id, current_user, db)
    return session


@router.post("/sessions", response_model=AttendanceSessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(payload: CreateSessionRequest, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    await _get_accessible_club(payload.club_id, current_user, db)
    session = AttendanceSession(club_id=payload.club_id, session_date=payload.session_date, created_by=current_user.id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/sessions/{session_id}/records", status_code=status.HTTP_200_OK)
async def bulk_mark(session_id: UUID, payload: BulkMarkRequest, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Mark (or update) attendance for many students at once, then recalculate PAJSK for each."""
    session = await _get_accessible_session(session_id, current_user, db)
    student_ids = [mark.student_id for mark in payload.records]
    if len(student_ids) != len(set(student_ids)):
        raise HTTPException(status_code=400, detail="A student can only be marked once per request")
    if student_ids:
        memberships = await db.execute(
            select(ClubMembership.student_id)
            .join(User, User.id == ClubMembership.student_id)
            .where(
                ClubMembership.club_id == session.club_id,
                ClubMembership.is_active == True,  # noqa: E712
                User.is_active == True,  # noqa: E712
                ClubMembership.student_id.in_(student_ids),
            )
        )
        if set(memberships.scalars().all()) != set(student_ids):
            raise HTTPException(status_code=400, detail="Attendance can only be marked for active club members")

    year = session.session_date.year

    newly_absent: list = []  # students who just became ABSENT (not re-saves of an existing absence)

    for mark in payload.records:
        existing = await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.session_id == session_id,
                AttendanceRecord.student_id == mark.student_id,
            )
        )
        record = existing.scalar_one_or_none()
        new_status = AttendanceStatus(mark.status)
        if new_status == AttendanceStatus.ABSENT and (record is None or record.status != AttendanceStatus.ABSENT):
            newly_absent.append(mark.student_id)
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

    # Notify student + parents (in-app + email) for anyone newly marked absent.
    if newly_absent:
        club = await db.get(Club, session.club_id)
        club_name = club.name if club else "your club"
        for student_id in newly_absent:
            student = await db.get(User, student_id)
            if student:
                await notify_absence(db, student, club_name, session.session_date.isoformat(), created_by=current_user.id)

    return {
        "detail": f"{len(payload.records)} attendance records saved",
        "absence_notices_sent": len(newly_absent),
    }


@router.get("/sessions", response_model=list[AttendanceSessionOut])
async def list_sessions(
    current_user: CurrentUser,
    club_id: UUID | None = None,
    session_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AttendanceSession)
    if current_user.role != UserRole.ADMIN:
        stmt = stmt.join(Club, Club.id == AttendanceSession.club_id).where(Club.coach_id == current_user.id)
    if club_id:
        stmt = stmt.where(AttendanceSession.club_id == club_id)
    if session_date:
        stmt = stmt.where(AttendanceSession.session_date == session_date)
    result = await db.execute(stmt.order_by(AttendanceSession.session_date.desc()))
    return result.scalars().all()


@router.get("/sessions/{session_id}/records", response_model=list[AttendanceRecordOut])
async def list_session_records(
    session_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _get_accessible_session(session_id, current_user, db)
    result = await db.execute(
        select(AttendanceRecord).where(AttendanceRecord.session_id == session_id)
    )
    return result.scalars().all()


@router.post("/sessions/{session_id}/recognize")
async def recognize_session_student(
    session_id: UUID,
    payload: FaceRecognitionRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Identify a face through the configured PAJSK service, restricted to this club's roster."""
    session = await _get_accessible_session(session_id, current_user, db)
    if not settings.PAJSK_FACE_SERVICE_URL or not settings.PAJSK_FACE_SERVICE_TOKEN:
        raise HTTPException(status_code=503, detail="Face recognition service is not configured")

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{settings.PAJSK_FACE_SERVICE_URL.rstrip('/')}/internal/recognize",
                json={"image": payload.image},
                headers={"Authorization": f"Bearer {settings.PAJSK_FACE_SERVICE_TOKEN}"},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Face recognition timed out; try again") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Face recognition service is unavailable") from exc

    if response.status_code in (401, 403):
        raise HTTPException(status_code=503, detail="Face recognition service token is not configured correctly")
    if response.status_code >= 500:
        raise HTTPException(status_code=503, detail="Face recognition service failed to process the image")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Face recognition service returned an error")
    try:
        match = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Face recognition service returned an invalid response") from exc

    if not isinstance(match, dict):
        raise HTTPException(status_code=502, detail="Face recognition service returned an invalid response")
    if match.get("status") == "unknown":
        return {"status": "unknown"}
    if match.get("status") != "found" or not isinstance(match.get("ic"), str):
        raise HTTPException(status_code=502, detail="Face recognition service returned an invalid response")
    ic_number = re.sub(r"\D", "", match["ic"])
    if not re.fullmatch(r"\d{12}", ic_number):
        raise HTTPException(status_code=502, detail="Face recognition service returned an invalid student identity")

    roster_result = await db.execute(
        select(User.id, User.full_name, StudentProfile.ic_number)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .join(ClubMembership, ClubMembership.student_id == User.id)
        .where(
            ClubMembership.club_id == session.club_id,
            ClubMembership.is_active == True,  # noqa: E712
            User.is_active == True,  # noqa: E712
        )
    )
    matches = {
        student_id: name
        for student_id, name, roster_ic in roster_result.all()
        if roster_ic and re.sub(r"\D", "", roster_ic) == ic_number
    }
    if not matches:
        return {"status": "not_in_roster"}
    if len(matches) != 1:
        return {"status": "ambiguous"}
    student_id, student_name = next(iter(matches.items()))
    return {"status": "found", "student_id": student_id, "student_name": student_name}
