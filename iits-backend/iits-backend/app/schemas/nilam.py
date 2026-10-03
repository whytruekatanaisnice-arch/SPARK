from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ORMBase


class NilamCreate(BaseModel):
    book_title: str
    author: str | None = None
    pages_read: int | None = None
    date_completed: date
    summary: str | None = None


class NilamOut(ORMBase):
    id: UUID
    student_id: UUID
    book_title: str
    author: str | None
    pages_read: int | None
    date_completed: date
    summary: str | None
