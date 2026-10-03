"""Announcements: admin creates/edits, everyone reads (filtered to their role/club)."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.announcement import Announcement
from app.models.club import ClubMembership
from app.schemas.announcement import AnnouncementCreate, AnnouncementOut, AnnouncementUpdate
from app.schemas.common import Message
from app.security import CurrentUser, require_admin

router = APIRouter(tags=["announcements"])


@router.get("/api/announcements", response_model=list[AnnouncementOut])
async def list_announcements(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Everyone sees school-wide announcements plus ones targeted at their role or their club."""
    my_club_ids: list[UUID] = []
    if current_user.role.value == "student":
        memberships = await db.execute(
            select(ClubMembership.club_id).where(ClubMembership.student_id == current_user.id, ClubMembership.is_active == True)  # noqa: E712
        )
        my_club_ids = [row[0] for row in memberships.all()]

    stmt = select(Announcement).where(
        or_(
            Announcement.target_roles.is_(None),
            Announcement.target_roles.contains([current_user.role.value]),
        )
    ).order_by(Announcement.published_at.desc())

    result = await db.execute(stmt)
    announcements = result.scalars().all()

    # Further filter club-scoped announcements to only the student's own clubs.
    return [a for a in announcements if a.club_id is None or a.club_id in my_club_ids or current_user.role.value != "student"]


admin_router = APIRouter(prefix="/api/admin/announcements", tags=["admin:announcements"], dependencies=[Depends(require_admin)])


@admin_router.post("", response_model=AnnouncementOut, status_code=status.HTTP_201_CREATED)
async def create_announcement(payload: AnnouncementCreate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    announcement = Announcement(**payload.model_dump(), created_by=current_user.id)
    db.add(announcement)
    await db.commit()
    await db.refresh(announcement)
    return announcement


@admin_router.patch("/{announcement_id}", response_model=AnnouncementOut)
async def update_announcement(announcement_id: UUID, payload: AnnouncementUpdate, db: AsyncSession = Depends(get_db)):
    announcement = await db.get(Announcement, announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(announcement, field, value)
    await db.commit()
    await db.refresh(announcement)
    return announcement


@admin_router.delete("/{announcement_id}", response_model=Message)
async def delete_announcement(announcement_id: UUID, db: AsyncSession = Depends(get_db)):
    announcement = await db.get(Announcement, announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    await db.delete(announcement)
    await db.commit()
    return Message(detail="Announcement deleted")
