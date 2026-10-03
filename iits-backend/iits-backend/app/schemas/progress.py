from uuid import UUID
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMBase


class ProgressCreate(BaseModel):
    student_id: UUID
    category: str = "general"
    note: str


class ProgressOut(ORMBase):
    id: UUID
    student_id: UUID
    coach_id: UUID
    category: str
    note: str
    created_at: datetime
