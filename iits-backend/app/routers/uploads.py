"""File uploads to the appropriate Supabase Storage buckets."""
import uuid
from urllib.parse import quote

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings
from app.models.user import User, UserRole
from app.security import CurrentUser

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

ALLOWED_CONTENT_TYPES = {
    "image/png", "image/jpeg", "image/webp", "image/gif",
    "application/pdf",
    "video/mp4", "video/quicktime", "video/webm",
}
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
EXTENSION_BY_CONTENT_TYPE = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "application/pdf": "pdf",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
}


async def _upload_file(file: UploadFile, current_user: User, bucket: str) -> dict[str, str]:
    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {content_type}")

    contents = await file.read(MAX_FILE_SIZE_BYTES + 1)
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 25MB limit")

    object_path = f"{current_user.id}/{uuid.uuid4()}.{EXTENSION_BY_CONTENT_TYPE[content_type]}"
    base_url = settings.SUPABASE_URL.rstrip("/")
    encoded_bucket = quote(bucket, safe="")
    encoded_path = quote(object_path, safe="/")
    upload_url = f"{base_url}/storage/v1/object/{encoded_bucket}/{encoded_path}"

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                upload_url,
                headers={
                    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                    "Content-Type": content_type,
                    "x-upsert": "false",
                },
                content=contents,
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Could not connect to Supabase Storage") from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Storage upload to bucket '{bucket}' failed ({response.status_code}): {response.text}",
        )

    public_url = f"{base_url}/storage/v1/object/public/{encoded_bucket}/{encoded_path}"
    return {"file_url": public_url}


@router.post("")
async def upload_submission_file(current_user: CurrentUser, file: UploadFile = File(...)):
    return await _upload_file(file, current_user, settings.SUPABASE_STORAGE_BUCKET)


@router.post("/absence-certificates")
async def upload_absence_certificate(current_user: CurrentUser, file: UploadFile = File(...)):
    if current_user.role not in (UserRole.STUDENT, UserRole.PARENT):
        raise HTTPException(
            status_code=403,
            detail="Only students or parents can upload absence certificates",
        )
    return await _upload_file(file, current_user, settings.SUPABASE_ABSENCE_CERTIFICATES_BUCKET)
