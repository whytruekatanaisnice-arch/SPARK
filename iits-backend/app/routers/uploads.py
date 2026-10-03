"""File uploads to Supabase Storage — used for task submissions (images/PDFs/videos)."""
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.config import settings
from app.security import CurrentUser

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

ALLOWED_CONTENT_TYPES = {
    "image/png", "image/jpeg", "image/webp", "image/gif",
    "application/pdf",
    "video/mp4", "video/quicktime", "video/webm",
}
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB


@router.post("")
async def upload_file(file: UploadFile, current_user: CurrentUser):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 25MB limit")

    ext = (file.filename or "").split(".")[-1] if "." in (file.filename or "") else "bin"
    object_path = f"{current_user.id}/{uuid.uuid4()}.{ext}"

    upload_url = f"{settings.SUPABASE_URL}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}/{object_path}"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            upload_url,
            headers={
                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": file.content_type,
                "x-upsert": "false",
            },
            content=contents,
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {response.text}")

    public_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/{settings.SUPABASE_STORAGE_BUCKET}/{object_path}"
    return {"file_url": public_url}
