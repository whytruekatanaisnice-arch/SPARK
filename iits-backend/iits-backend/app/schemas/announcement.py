from uuid import UUID
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMBase


class AnnouncementCreate(BaseModel):
    title: str
    body: str
    target_roles: list[str] | None = None  # e.g. ["student","parent"]; None = everyone
    club_id: UUID | None = None


class AnnouncementUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    target_roles: list[str] | None = None


class AnnouncementOut(ORMBase):
    id: UUID
    title: str
    body: str
    target_roles: list[str] | None
    club_id: UUID | None
    published_at: datetime
