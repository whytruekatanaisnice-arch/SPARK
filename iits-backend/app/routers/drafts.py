"""Authenticated users' private, page-scoped autosave drafts."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.draft import AutosaveDraft
from app.schemas.common import Message
from app.schemas.draft import DraftUpdate
from app.security import CurrentUser

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


def _validate_page_key(page_key: str) -> None:
    if (
        not page_key.startswith("/")
        or page_key.startswith("//")
        or any(ord(char) < 33 or char in "\\#" for char in page_key)
    ):
        raise HTTPException(status_code=422, detail="Invalid draft page key")


@router.get("")
async def get_draft(
    current_user: CurrentUser,
    page_key: str = Query(min_length=1, max_length=512),
    db: AsyncSession = Depends(get_db),
):
    _validate_page_key(page_key)
    result = await db.execute(
        select(AutosaveDraft).where(
            AutosaveDraft.user_id == current_user.id,
            AutosaveDraft.page_key == page_key,
        )
    )
    draft = result.scalar_one_or_none()
    return {"page_key": page_key, "data": draft.data if draft else {}}


@router.put("")
async def save_draft(
    current_user: CurrentUser,
    payload: DraftUpdate,
    page_key: str = Query(min_length=1, max_length=512),
    db: AsyncSession = Depends(get_db),
):
    _validate_page_key(page_key)
    statement = insert(AutosaveDraft).values(
        user_id=current_user.id,
        page_key=page_key,
        data=payload.data,
    )
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[AutosaveDraft.user_id, AutosaveDraft.page_key],
            set_={
                "data": AutosaveDraft.data.op("||")(statement.excluded.data),
                "updated_at": func.now(),
            },
        )
    )
    await db.commit()
    return {"detail": "Draft saved"}


@router.delete("")
async def delete_draft(
    current_user: CurrentUser,
    page_key: str = Query(min_length=1, max_length=512),
    db: AsyncSession = Depends(get_db),
):
    _validate_page_key(page_key)
    await db.execute(
        delete(AutosaveDraft).where(
            AutosaveDraft.user_id == current_user.id,
            AutosaveDraft.page_key == page_key,
        )
    )
    await db.commit()
    return Message(detail="Draft cleared")
