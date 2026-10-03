from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ORMBase


class CreateSessionRequest(BaseModel):
    club_id: UUID
    session_date: date


class AttendanceMark(BaseModel):
    student_id: UUID
    status: str  # present | absent | excused | late
    note: str | None = None
    marked_via: str = "checklist"  # or "qr"


class BulkMarkRequest(BaseModel):
    records: list[AttendanceMark]


class AttendanceSessionOut(ORMBase):
    id: UUID
    club_id: UUID
    session_date: date


class AttendanceRecordOut(ORMBase):
    id: UUID
    session_id: UUID
    student_id: UUID
    status: str
    note: str | None
    marked_via: str
