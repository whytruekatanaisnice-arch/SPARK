from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ORMBase


class CompetitionOut(ORMBase):
    id: UUID
    name: str
    description: str | None
    start_date: date
    end_date: date


class CompetitionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
