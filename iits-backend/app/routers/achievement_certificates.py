"""OCR and review workflow for verified competition-certificate PAJSK scores."""
import hashlib
import logging
import re
import unicodedata
import uuid
from datetime import date, datetime, timezone
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.achievement_certificate import CompetitionCertificate, CompetitionCertificateStatus
from app.models.notification import Notification
from app.models.user import ParentStudentLink, User, UserRole
from app.schemas.achievement_certificate import (
    CertificateReview,
    CertificateReviewItem,
    CertificateSubmissionOut,
    CertificateSubmit,
)
from app.security import CurrentUser, require_any, require_coach, require_parent, require_student
from app.utils.email import send_email
from app.utils.certificate_ocr_extraction import extract_certificate_fields
from app.utils.pajsk_certificate_scoring import calculate_certificate_score

logger = logging.getLogger(__name__)

student_router = APIRouter(
    prefix="/api/student/achievement-certificates",
    tags=["student:achievement-certificates"],
    dependencies=[Depends(require_student)],
)
parent_router = APIRouter(
    prefix="/api/parent/children/{student_id}/achievement-certificates",
    tags=["parent:achievement-certificates"],
    dependencies=[Depends(require_parent)],
)
review_router = APIRouter(
    prefix="/api/coach/certificate-submissions",
    tags=["coach:certificate-submissions"],
    dependencies=[Depends(require_coach)],
)
scoring_router = APIRouter(
    prefix="/api/achievement-certificate-scoring",
    tags=["achievement-certificate-scoring"],
    dependencies=[Depends(require_any)],
)

MAX_CERTIFICATE_SIZE = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "application/pdf": ("pdf", b"%PDF-"),
    "image/jpeg": ("jpg", b"\xff\xd8\xff"),
    "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
}
DUPLICATE_ACTIVE_STATUSES = (
    CompetitionCertificateStatus.PENDING,
    CompetitionCertificateStatus.APPROVED,
)


@scoring_router.get("")
async def certificate_scoring_guide():
    from app.utils.pajsk_certificate_scoring import ACHIEVEMENT_SCORES, ENGAGEMENT_SCORES

    levels = {
        "international": "Antarabangsa",
        "national": "Kebangsaan",
        "state": "Negeri",
        "district": "Daerah / Zon",
        "school": "Sekolah",
    }
    return {
        "levels": levels,
        "participation_types": {
            "I": "Ranked event/course; in person, or online with live interaction and ranking",
            "II": "In person or online without ranking; also organizers, technical staff, performers, and international-visit participants",
            "III": "Online without live interaction, including supporters or audience",
        },
        "placements": {
            "champion": "Johan",
            "runner_up": "Naib Johan",
            "third": "Ketiga",
            "fourth": "Keempat",
            "fifth": "Kelima",
        },
        "engagement": {
            level.value: {kind.value: score for kind, score in scores.items()}
            for level, scores in ENGAGEMENT_SCORES.items()
        },
        "achievement": {
            level.value: {placement.value: score for placement, score in scores.items()}
            for level, scores in ACHIEVEMENT_SCORES.items()
        },
    }


async def _assert_parent_child(parent_id: uuid.UUID, student_id: uuid.UUID, db: AsyncSession) -> User:
    result = await db.execute(
        select(User)
        .join(ParentStudentLink, ParentStudentLink.student_id == User.id)
        .where(
            ParentStudentLink.parent_id == parent_id,
            ParentStudentLink.student_id == student_id,
            User.role == UserRole.STUDENT,
            User.is_active.is_(True),
        )
    )
    student = result.scalar_one_or_none()
    if student is None:
        raise HTTPException(status_code=403, detail="Not authorized to submit for this student")
    return student


def _normalize_event_name(event_name: str) -> str:
    normalized = unicodedata.normalize("NFKC", event_name).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", normalized).split())


async def _read_certificate(file: UploadFile) -> tuple[bytes, str, str]:
    file_type = ALLOWED_CONTENT_TYPES.get(file.content_type or "")
    if file_type is None:
        raise HTTPException(status_code=400, detail="Certificate must be a PDF, JPEG, or PNG")
    contents = await file.read(MAX_CERTIFICATE_SIZE + 1)
    if len(contents) > MAX_CERTIFICATE_SIZE:
        raise HTTPException(status_code=400, detail="Certificate exceeds the 10MB limit")
    extension, signature = file_type
    if not contents.startswith(signature):
        raise HTTPException(status_code=400, detail="Certificate content does not match its file type")
    return contents, extension, hashlib.sha256(contents).hexdigest()


async def _active_duplicate(
    student_id: uuid.UUID,
    file_sha256: str,
    db: AsyncSession,
) -> bool:
    result = await db.execute(
        select(CompetitionCertificate.id).where(
            CompetitionCertificate.student_id == student_id,
            CompetitionCertificate.file_sha256 == file_sha256,
            CompetitionCertificate.status.in_(DUPLICATE_ACTIVE_STATUSES),
        )
    )
    return result.scalar_one_or_none() is not None


async def _run_ocr(contents: bytes, extension: str, content_type: str) -> str:
    if not settings.OCR_SPACE_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OCR is not configured; set OCR_SPACE_API_KEY in the backend environment",
        )
    ocr_parameters = {
        "OCREngine": "2",
        "isOverlayRequired": "false",
        "scale": "true",
        "detectOrientation": "true",
    }
    language = settings.OCR_SPACE_LANGUAGE.strip()
    if language and language.casefold() != "auto":
        ocr_parameters["language"] = language
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.ocr.space/parse/image",
                headers={"apikey": settings.OCR_SPACE_API_KEY},
                data=ocr_parameters,
                files={"file": (f"certificate.{extension}", contents, content_type)},
            )
    except httpx.RequestError as exc:
        logger.error("OCR.space request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="OCR service is unavailable; try again later") from exc
    if response.status_code >= 400:
        logger.error("OCR.space returned HTTP status %s", response.status_code)
        raise HTTPException(status_code=502, detail="OCR service could not process this certificate")
    try:
        result = response.json()
    except ValueError as exc:
        logger.error("OCR.space returned invalid JSON")
        raise HTTPException(status_code=502, detail="OCR service returned an invalid response") from exc
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="OCR service returned an invalid response")
    if result.get("IsErroredOnProcessing"):
        raw_error = result.get("ErrorMessage")
        if isinstance(raw_error, list):
            provider_error = "; ".join(str(message) for message in raw_error if message)
        elif isinstance(raw_error, str):
            provider_error = raw_error
        else:
            provider_error = ""
        provider_error = " ".join(provider_error.split())[:300]
        if provider_error:
            logger.warning("OCR.space rejected the certificate: %s", provider_error)
            detail = f"OCR.space could not process this upload: {provider_error}"
        else:
            logger.warning("OCR.space rejected the certificate without an error message")
            detail = "OCR.space could not process this upload; try a clearer PDF or image"
        raise HTTPException(status_code=422, detail=detail)
    parsed_results = result.get("ParsedResults") or []
    ocr_text = "\n".join(
        page.get("ParsedText", "").strip()
        for page in parsed_results
        if isinstance(page, dict) and isinstance(page.get("ParsedText"), str)
    ).strip()
    if not ocr_text:
        raise HTTPException(status_code=422, detail="No text could be read; upload a clearer certificate")
    if len(ocr_text) > 50_000:
        ocr_text = ocr_text[:50_000]
    return ocr_text


async def _store_file(contents: bytes, extension: str, content_type: str, uploader_id: uuid.UUID) -> str:
    object_path = f"{uploader_id}/{uuid.uuid4()}.{extension}"
    url = (
        f"{settings.SUPABASE_URL}/storage/v1/object/"
        f"{quote(settings.SUPABASE_ACHIEVEMENT_CERTIFICATES_BUCKET, safe='')}/"
        f"{quote(object_path, safe='/')}"
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                    "Content-Type": content_type,
                    "x-upsert": "false",
                },
                content=contents,
            )
    except httpx.RequestError as exc:
        logger.error("Supabase achievement certificate upload failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Certificate storage is unavailable") from exc
    if response.status_code >= 400:
        logger.error("Supabase certificate upload returned status %s", response.status_code)
        raise HTTPException(status_code=502, detail="Could not store the certificate securely")
    return object_path


async def _remove_stored_file(object_path: str) -> None:
    url = (
        f"{settings.SUPABASE_URL}/storage/v1/object/"
        f"{quote(settings.SUPABASE_ACHIEVEMENT_CERTIFICATES_BUCKET, safe='')}/"
        f"{quote(object_path, safe='/')}"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.delete(
                url,
                headers={
                    "Authorization": f"******",
                    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                },
            )
    except httpx.RequestError as exc:
        logger.error("Could not clean up orphaned certificate file: %s", type(exc).__name__)
        return
    if response.status_code >= 400:
        logger.error("Orphaned certificate cleanup returned status %s", response.status_code)


async def _create_ocr_draft(
    student: User,
    uploader: User,
    file: UploadFile,
    db: AsyncSession,
) -> dict:
    contents, extension, file_sha256 = await _read_certificate(file)
    if await _active_duplicate(student.id, file_sha256, db):
        raise HTTPException(status_code=409, detail="This certificate has already been submitted for this student")

    ocr_text = await _run_ocr(contents, extension, file.content_type or "")
    file_path = await _store_file(contents, extension, file.content_type or "", uploader.id)
    draft = CompetitionCertificate(
        student_id=student.id,
        submitted_by=uploader.id,
        status=CompetitionCertificateStatus.DRAFT,
        file_path=file_path,
        file_sha256=file_sha256,
        ocr_text=ocr_text,
    )
    db.add(draft)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        await _remove_stored_file(file_path)
        logger.exception("Could not save OCR draft for student %s", student.id)
        raise HTTPException(status_code=500, detail="Could not save the certificate draft")
    await db.refresh(draft)
    suggested_fields = extract_certificate_fields(draft.ocr_text)
    return {
        "draft_id": draft.id,
        "ocr_text": draft.ocr_text,
        "suggested_fields": suggested_fields,
        "student_name": student.full_name,
        "message": "OCR complete. Verify every field against the certificate before submitting.",
    }


async def _get_owned_draft(
    draft_id: uuid.UUID,
    student_id: uuid.UUID,
    uploader_id: uuid.UUID,
    db: AsyncSession,
) -> CompetitionCertificate:
    result = await db.execute(
        select(CompetitionCertificate)
        .where(
            CompetitionCertificate.id == draft_id,
            CompetitionCertificate.student_id == student_id,
            CompetitionCertificate.submitted_by == uploader_id,
            CompetitionCertificate.status == CompetitionCertificateStatus.DRAFT,
        )
        .with_for_update()
    )
    draft = result.scalar_one_or_none()
    if draft is None:
        raise HTTPException(status_code=404, detail="Certificate draft not found or already submitted")
    return draft


async def _is_duplicate_event(
    student_id: uuid.UUID,
    event_date: date,
    event_key: str,
    excluding_id: uuid.UUID,
    db: AsyncSession,
) -> bool:
    result = await db.execute(
        select(CompetitionCertificate.id).where(
            CompetitionCertificate.student_id == student_id,
            CompetitionCertificate.event_date == event_date,
            CompetitionCertificate.event_key == event_key,
            CompetitionCertificate.status.in_(DUPLICATE_ACTIVE_STATUSES),
            CompetitionCertificate.id != excluding_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def _queue_reviewer_notifications(
    student: User,
    submitter: User,
    event_name: str,
    db: AsyncSession,
) -> list[User]:
    staff_result = await db.execute(
        select(User).where(
            User.role.in_((UserRole.ADMIN, UserRole.COACH)),
            User.is_active.is_(True),
        )
    )
    staff = staff_result.scalars().all()
    for reviewer in staff:
        db.add(Notification(
            user_id=reviewer.id,
            title="Competition certificate needs review",
            body=f"{student.full_name} submitted {event_name} for PAJSK verification.",
            created_by=submitter.id,
        ))
    return staff


async def _email_reviewers(staff: list[User], student: User, event_name: str) -> None:
    message = (
        f"{student.full_name} submitted the competition certificate for {event_name}. "
        f"Sign in to review the OCR fields and certificate: {settings.APP_LOGIN_URL}"
    )
    for reviewer in staff:
        if not await send_email(reviewer.email, "PAJSK certificate requires review", message):
            logger.warning("Competition certificate alert email failed for reviewer %s", reviewer.id)


async def _notify_student_family(
    student_id: uuid.UUID,
    title: str,
    body: str,
    subject: str,
    db: AsyncSession,
) -> None:
    student = await db.get(User, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    parents_result = await db.execute(
        select(User)
        .join(ParentStudentLink, ParentStudentLink.parent_id == User.id)
        .where(
            ParentStudentLink.student_id == student_id,
            User.role == UserRole.PARENT,
            User.is_active.is_(True),
        )
    )
    recipients = {user.id: user for user in [student, *parents_result.scalars().all()] if user.is_active}
    for recipient in recipients.values():
        db.add(Notification(user_id=recipient.id, title=title, body=body))
    await db.commit()
    email_body = f"{body}\n\nSign in to IITS for details:\n{settings.APP_LOGIN_URL}"
    for recipient in recipients.values():
        if not await send_email(recipient.email, subject, email_body):
            logger.warning("PAJSK certificate status email failed for user %s", recipient.id)


@student_router.post("/ocr")
async def student_certificate_ocr(
    current_user: CurrentUser,
    file: UploadFile = File(),
    db: AsyncSession = Depends(get_db),
):
    return await _create_ocr_draft(current_user, current_user, file, db)


@parent_router.post("/ocr")
async def parent_certificate_ocr(
    student_id: uuid.UUID,
    current_user: CurrentUser,
    file: UploadFile = File(),
    db: AsyncSession = Depends(get_db),
):
    student = await _assert_parent_child(current_user.id, student_id, db)
    return await _create_ocr_draft(student, current_user, file, db)


@student_router.get("/drafts")
async def list_student_certificate_drafts(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CompetitionCertificate)
        .where(
            CompetitionCertificate.student_id == current_user.id,
            CompetitionCertificate.submitted_by == current_user.id,
            CompetitionCertificate.status == CompetitionCertificateStatus.DRAFT,
        )
        .order_by(CompetitionCertificate.created_at.desc())
    )
    return [
        {
            "draft_id": draft.id,
            "ocr_text": draft.ocr_text,
            "suggested_fields": extract_certificate_fields(draft.ocr_text),
            "created_at": draft.created_at,
        }
        for draft in result.scalars().all()
    ]


@parent_router.get("/drafts")
async def list_parent_certificate_drafts(
    student_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _assert_parent_child(current_user.id, student_id, db)
    result = await db.execute(
        select(CompetitionCertificate)
        .where(
            CompetitionCertificate.student_id == student_id,
            CompetitionCertificate.submitted_by == current_user.id,
            CompetitionCertificate.status == CompetitionCertificateStatus.DRAFT,
        )
        .order_by(CompetitionCertificate.created_at.desc())
    )
    return [
        {
            "draft_id": draft.id,
            "ocr_text": draft.ocr_text,
            "suggested_fields": extract_certificate_fields(draft.ocr_text),
            "created_at": draft.created_at,
        }
        for draft in result.scalars().all()
    ]


@student_router.get("", response_model=list[CertificateSubmissionOut])
async def list_student_submissions(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CompetitionCertificate)
        .where(
            CompetitionCertificate.student_id == current_user.id,
            CompetitionCertificate.status != CompetitionCertificateStatus.DRAFT,
        )
        .order_by(CompetitionCertificate.created_at.desc())
    )
    return result.scalars().all()


@parent_router.get("", response_model=list[CertificateSubmissionOut])
async def list_child_submissions(
    student_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _assert_parent_child(current_user.id, student_id, db)
    result = await db.execute(
        select(CompetitionCertificate)
        .where(
            CompetitionCertificate.student_id == student_id,
            CompetitionCertificate.status != CompetitionCertificateStatus.DRAFT,
        )
        .order_by(CompetitionCertificate.created_at.desc())
    )
    return result.scalars().all()


@student_router.get("/{draft_id}/duplicate-check")
async def student_duplicate_check(
    draft_id: uuid.UUID,
    current_user: CurrentUser,
    event_name: str = Query(min_length=3, max_length=255),
    event_date: date = Query(),
    db: AsyncSession = Depends(get_db),
):
    draft = await _get_owned_draft(draft_id, current_user.id, current_user.id, db)
    duplicate = await _is_duplicate_event(
        draft.student_id, event_date, _normalize_event_name(event_name), draft.id, db
    )
    return {"duplicate": duplicate}


@parent_router.get("/{draft_id}/duplicate-check")
async def parent_duplicate_check(
    student_id: uuid.UUID,
    draft_id: uuid.UUID,
    current_user: CurrentUser,
    event_name: str = Query(min_length=3, max_length=255),
    event_date: date = Query(),
    db: AsyncSession = Depends(get_db),
):
    await _assert_parent_child(current_user.id, student_id, db)
    draft = await _get_owned_draft(draft_id, student_id, current_user.id, db)
    duplicate = await _is_duplicate_event(
        draft.student_id, event_date, _normalize_event_name(event_name), draft.id, db
    )
    return {"duplicate": duplicate}


async def _submit_draft(
    draft_id: uuid.UUID,
    student: User,
    submitter: User,
    payload: CertificateSubmit,
    db: AsyncSession,
) -> CompetitionCertificate:
    draft = await _get_owned_draft(draft_id, student.id, submitter.id, db)
    event_key = _normalize_event_name(payload.event_name)
    if await _active_duplicate(student.id, draft.file_sha256, db):
        raise HTTPException(status_code=409, detail="This certificate has already been submitted for this student")
    if await _is_duplicate_event(student.id, payload.event_date, event_key, draft.id, db):
        raise HTTPException(status_code=409, detail="This student already submitted this event certificate")

    engagement_score, achievement_score, total_score = calculate_certificate_score(
        payload.competition_level,
        payload.participation_type,
        payload.placement,
    )
    draft.event_name = payload.event_name
    draft.event_key = event_key
    draft.organizer = payload.organizer
    draft.awardee_name = payload.awardee_name
    draft.event_date = payload.event_date
    draft.competition_level = payload.competition_level.value
    draft.participation_type = payload.participation_type.value
    draft.placement = payload.placement.value if payload.placement else None
    draft.engagement_score = engagement_score
    draft.achievement_score = achievement_score
    draft.score = total_score
    draft.status = CompetitionCertificateStatus.PENDING
    try:
        reviewers = await _queue_reviewer_notifications(student, submitter, draft.event_name, db)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A matching certificate was submitted at the same time") from exc
    await db.refresh(draft)
    await _email_reviewers(reviewers, student, draft.event_name)
    return draft


@student_router.post("/{draft_id}/submit", response_model=CertificateSubmissionOut, status_code=201)
async def submit_student_certificate(
    draft_id: uuid.UUID,
    payload: CertificateSubmit,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    return await _submit_draft(draft_id, current_user, current_user, payload, db)


@parent_router.post("/{draft_id}/submit", response_model=CertificateSubmissionOut, status_code=201)
async def submit_parent_certificate(
    student_id: uuid.UUID,
    draft_id: uuid.UUID,
    payload: CertificateSubmit,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    student = await _assert_parent_child(current_user.id, student_id, db)
    return await _submit_draft(draft_id, student, current_user, payload, db)


@review_router.get("", response_model=list[CertificateReviewItem])
async def list_certificate_reviews(
    status: CompetitionCertificateStatus | None = None,
    db: AsyncSession = Depends(get_db),
):
    statement = (
        select(CompetitionCertificate, User.full_name, User.email)
        .join(User, User.id == CompetitionCertificate.student_id)
        .where(CompetitionCertificate.status != CompetitionCertificateStatus.DRAFT)
        .order_by(CompetitionCertificate.created_at.desc())
    )
    if status is not None:
        statement = statement.where(CompetitionCertificate.status == status)
    result = await db.execute(statement)
    return [
        CertificateReviewItem(
            **CertificateSubmissionOut.model_validate(item).model_dump(),
            student_name=student_name,
            student_email=student_email,
            ocr_text=item.ocr_text,
        )
        for item, student_name, student_email in result.all()
    ]


@review_router.get("/{submission_id}/file")
async def get_submitted_certificate_file(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    certificate = await db.get(CompetitionCertificate, submission_id)
    if certificate is None or certificate.status == CompetitionCertificateStatus.DRAFT:
        raise HTTPException(status_code=404, detail="Certificate submission not found")
    url = (
        f"{settings.SUPABASE_URL}/storage/v1/object/sign/"
        f"{quote(settings.SUPABASE_ACHIEVEMENT_CERTIFICATES_BUCKET, safe='')}/"
        f"{quote(certificate.file_path, safe='/')}"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                },
                json={"expiresIn": 300},
            )
    except httpx.RequestError as exc:
        logger.error("Certificate signed URL request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Certificate storage is unavailable") from exc
    if response.status_code >= 400:
        logger.error("Certificate signed URL returned status %s", response.status_code)
        raise HTTPException(status_code=502, detail="Could not create a temporary certificate link")
    try:
        storage_result = response.json()
    except ValueError as exc:
        logger.error("Certificate signed URL response was invalid")
        raise HTTPException(status_code=502, detail="Could not create a temporary certificate link") from exc
    signed_url = storage_result.get("signedURL") if isinstance(storage_result, dict) else None
    if not isinstance(signed_url, str) or not signed_url:
        raise HTTPException(status_code=502, detail="Could not create a temporary certificate link")
    if not signed_url.startswith(("https://", "http://")):
        signed_url = f"{settings.SUPABASE_URL}/storage/v1/{signed_url.lstrip('/')}"
    return {"url": signed_url, "expires_in": 300}


@review_router.patch("/{submission_id}", response_model=CertificateSubmissionOut)
async def review_certificate_submission(
    submission_id: uuid.UUID,
    payload: CertificateReview,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CompetitionCertificate)
        .where(CompetitionCertificate.id == submission_id)
        .with_for_update()
    )
    certificate = result.scalar_one_or_none()
    if certificate is None or certificate.status == CompetitionCertificateStatus.DRAFT:
        raise HTTPException(status_code=404, detail="Certificate submission not found")
    if certificate.status != CompetitionCertificateStatus.PENDING:
        raise HTTPException(status_code=409, detail="This certificate was already reviewed")

    certificate.status = payload.status
    certificate.review_note = payload.review_note.strip() if payload.review_note else None
    certificate.reviewed_by = current_user.id
    certificate.reviewed_at = datetime.now(timezone.utc)
    action = "approved" if payload.status == CompetitionCertificateStatus.APPROVED else "rejected"
    body = f"The certificate for {certificate.event_name} was {action}."
    if certificate.review_note:
        body += f" Review note: {certificate.review_note}"
    await _notify_student_family(
        certificate.student_id,
        f"PAJSK certificate {action}",
        body,
        f"PAJSK certificate {action}",
        db,
    )
    await db.commit()
    await db.refresh(certificate)
    if payload.status == CompetitionCertificateStatus.APPROVED:
        from app.utils.pa_jsK import recalculate_and_store

        await recalculate_and_store(certificate.student_id, date.today().year, db)
    return certificate
