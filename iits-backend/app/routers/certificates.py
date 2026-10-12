"""
Absence certificate workflow.

  student/parent  -> submit a certificate (optionally tied to a specific absence)
  admin           -> gets notified, reviews, approves or rejects
  on approval     -> linked attendance record becomes EXCUSED, PAJSK is recalculated
  on any decision -> student + parents are notified (in-app + email)
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.attendance import AttendanceRecord, AttendanceSession, AttendanceStatus
from app.models.certificate import AbsenceCertificate, CertificateStatus
from app.models.club import Club
from app.models.user import ParentStudentLink, StudentProfile, User
from app.schemas.certificate import CertificateAdminOut, CertificateCreate, CertificateOut, CertificateReview
from app.security import CurrentUser, require_admin, require_parent, require_student
from app.utils.notifier import notify_admins_new_certificate, notify_certificate_decision
from app.utils.pa_jsK import recalculate_and_store

student_router = APIRouter(prefix="/api/student/certificates", tags=["student:certificates"], dependencies=[Depends(require_student)])
parent_router = APIRouter(prefix="/api/parent", tags=["parent:certificates"], dependencies=[Depends(require_parent)])
admin_router = APIRouter(prefix="/api/admin/certificates", tags=["admin:certificates"], dependencies=[Depends(require_admin)])


async def _absence_context(db: AsyncSession, record_id: UUID | None) -> tuple[str, str | None]:
    """(club_name, session_date_iso) for an attendance record, or ("General absence", None)."""
    if not record_id:
        return "General absence", None
    row = (await db.execute(
        select(Club.name, AttendanceSession.session_date)
        .select_from(AttendanceRecord)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .join(Club, Club.id == AttendanceSession.club_id)
        .where(AttendanceRecord.id == record_id)
    )).first()
    return (row[0], row[1].isoformat()) if row else ("General absence", None)


async def _create_certificate(db: AsyncSession, student_id: UUID, submitter: User, payload: CertificateCreate) -> AbsenceCertificate:
    if payload.attendance_record_id:
        record = await db.get(AttendanceRecord, payload.attendance_record_id)
        if not record or record.student_id != student_id:
            raise HTTPException(status_code=400, detail="That attendance record doesn't belong to this student")
        existing = (await db.execute(
            select(AbsenceCertificate).where(
                AbsenceCertificate.attendance_record_id == payload.attendance_record_id,
                AbsenceCertificate.status == CertificateStatus.PENDING,
            )
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="A certificate for this absence is already awaiting review")

    cert = AbsenceCertificate(
        student_id=student_id, submitted_by=submitter.id, attendance_record_id=payload.attendance_record_id,
        reason=payload.reason, file_url=payload.file_url,
    )
    db.add(cert)
    await db.commit()
    await db.refresh(cert)

    student = await db.get(User, student_id)
    club_name, _ = await _absence_context(db, payload.attendance_record_id)
    await notify_admins_new_certificate(db, student, club_name, payload.reason, created_by=submitter.id)
    return cert


# ---------------- Student ----------------

@student_router.post("", response_model=CertificateOut, status_code=status.HTTP_201_CREATED)
async def student_submit(payload: CertificateCreate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return await _create_certificate(db, current_user.id, current_user, payload)


@student_router.get("", response_model=list[CertificateOut])
async def student_list(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AbsenceCertificate).where(AbsenceCertificate.student_id == current_user.id).order_by(AbsenceCertificate.created_at.desc())
    )
    return result.scalars().all()


# ---------------- Parent ----------------

async def _assert_my_child(db: AsyncSession, parent_id: UUID, student_id: UUID) -> None:
    link = await db.execute(select(ParentStudentLink).where(
        ParentStudentLink.parent_id == parent_id, ParentStudentLink.student_id == student_id))
    if not link.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not authorized for this student")


@parent_router.post("/children/{student_id}/certificates", response_model=CertificateOut, status_code=status.HTTP_201_CREATED)
async def parent_submit(student_id: UUID, payload: CertificateCreate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    await _assert_my_child(db, current_user.id, student_id)
    return await _create_certificate(db, student_id, current_user, payload)


@parent_router.get("/children/{student_id}/certificates", response_model=list[CertificateOut])
async def parent_list(student_id: UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    await _assert_my_child(db, current_user.id, student_id)
    result = await db.execute(
        select(AbsenceCertificate).where(AbsenceCertificate.student_id == student_id).order_by(AbsenceCertificate.created_at.desc())
    )
    return result.scalars().all()


@parent_router.get("/children/{student_id}/absences")
async def parent_child_absences(student_id: UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Absent records for a child — used to pick which absence a certificate is for."""
    await _assert_my_child(db, current_user.id, student_id)
    return await _absences_for(db, student_id)


async def _absences_for(db: AsyncSession, student_id: UUID) -> list[dict]:
    rows = (await db.execute(
        select(AttendanceRecord.id, AttendanceSession.session_date, Club.name)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .join(Club, Club.id == AttendanceSession.club_id)
        .where(AttendanceRecord.student_id == student_id, AttendanceRecord.status == AttendanceStatus.ABSENT)
        .order_by(AttendanceSession.session_date.desc())
    )).all()
    return [{"record_id": str(rid), "session_date": d.isoformat(), "club_name": name} for rid, d, name in rows]


@student_router.get("/absences", tags=["student:certificates"])
async def student_absences(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return await _absences_for(db, current_user.id)


# ---------------- Admin ----------------

@admin_router.get("", response_model=list[CertificateAdminOut])
async def admin_list(status_filter: str | None = "pending", db: AsyncSession = Depends(get_db)):
    """status_filter: pending (default) | approved | rejected | all"""
    stmt = select(AbsenceCertificate).order_by(AbsenceCertificate.created_at.desc())
    if status_filter and status_filter != "all":
        if status_filter not in [m.value for m in CertificateStatus]:
            raise HTTPException(status_code=400, detail="status_filter must be pending, approved, rejected or all")
        stmt = stmt.where(AbsenceCertificate.status == CertificateStatus(status_filter))
    certs = (await db.execute(stmt)).scalars().all()

    out: list[CertificateAdminOut] = []
    for c in certs:
        student = await db.get(User, c.student_id)
        profile = (await db.execute(select(StudentProfile).where(StudentProfile.user_id == c.student_id))).scalar_one_or_none()
        submitter = await db.get(User, c.submitted_by)
        club_name, session_date = await _absence_context(db, c.attendance_record_id)
        item = CertificateAdminOut.model_validate(c)
        item.status = c.status.value
        item.student_name = student.full_name if student else None
        item.student_number = profile.student_number if profile else None
        item.submitted_by_name = submitter.full_name if submitter else None
        item.club_name = club_name
        item.session_date = session_date
        out.append(item)
    return out


@admin_router.patch("/{certificate_id}", response_model=CertificateOut)
async def admin_review(certificate_id: UUID, payload: CertificateReview, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if payload.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be 'approved' or 'rejected'")

    cert = await db.get(AbsenceCertificate, certificate_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if cert.status != CertificateStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Already {cert.status.value}")

    approved = payload.status == "approved"
    cert.status = CertificateStatus.APPROVED if approved else CertificateStatus.REJECTED
    cert.reviewed_by = current_user.id
    cert.reviewed_at = datetime.now(timezone.utc)
    cert.review_note = payload.review_note

    if approved and cert.attendance_record_id:
        record = await db.get(AttendanceRecord, cert.attendance_record_id)
        if record:
            record.status = AttendanceStatus.EXCUSED
            record.note = f"Certificate approved: {cert.reason}"
    await db.commit()
    await db.refresh(cert)

    if approved and cert.attendance_record_id:
        record = await db.get(AttendanceRecord, cert.attendance_record_id)
        session = await db.get(AttendanceSession, record.session_id) if record else None
        if session:
            await recalculate_and_store(cert.student_id, session.session_date.year, db)

    student = await db.get(User, cert.student_id)
    await notify_certificate_decision(db, student, approved, payload.review_note, created_by=current_user.id)
    return cert
