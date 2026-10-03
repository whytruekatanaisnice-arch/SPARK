from uuid import UUID
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMBase


class NotificationBroadcast(BaseModel):
    title: str
    body: str
    # target one club's members/parents, or explicit user ids
    club_id: UUID | None = None
    user_ids: list[UUID] | None = None
    audience: str = "students"  # students | parents | both


class NotificationOut(ORMBase):
    id: UUID
    user_id: UUID
    title: str
    body: str
    is_read: bool
    created_at: datetime
