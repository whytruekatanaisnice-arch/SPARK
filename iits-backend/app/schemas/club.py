from datetime import time
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ORMBase


class VenueCreate(BaseModel):
    name: str
    capacity: int | None = None
    notes: str | None = None


class VenueOut(ORMBase):
    id: UUID
    name: str
    capacity: int | None
    notes: str | None


class ScheduleSlot(BaseModel):
    day_of_week: str  # MON..SUN
    start_time: time
    end_time: time


class ClubCreate(BaseModel):
    name: str
    category: str | None = None
    description: str | None = None
    coach_id: UUID | None = None
    venue_id: UUID | None = None
    schedules: list[ScheduleSlot] = []


class ClubUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    description: str | None = None
    coach_id: UUID | None = None
    venue_id: UUID | None = None
    is_active: bool | None = None


class ClubOut(ORMBase):
    id: UUID
    name: str
    category: str | None
    description: str | None
    coach_id: UUID | None
    venue_id: UUID | None
    is_active: bool


class AssignVenueRequest(BaseModel):
    venue_id: UUID
