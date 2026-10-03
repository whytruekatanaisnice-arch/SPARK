from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ORMBase


class AchievementRankOut(ORMBase):
    id: UUID
    name: str
    pajsk_points: int


class AchievementCreate(BaseModel):
    club_id: UUID
    student_id: UUID
    rank_id: UUID
    competition_name: str
    level: str | None = None
    event_date: date | None = None


class AchievementOut(ORMBase):
    id: UUID
    club_id: UUID
    student_id: UUID
    rank_id: UUID
    competition_name: str
    level: str | None
    event_date: date | None
