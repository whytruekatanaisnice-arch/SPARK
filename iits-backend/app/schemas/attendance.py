from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMBase


class CreateSessionRequest(BaseModel):
    club_id: UUID
    session_date: date


class AttendanceMark(BaseModel):
    student_id: UUID
    status: Literal["present", "absent", "excused", "late"]
    note: str | None = None
    marked_via: str = "checklist"


class BulkMarkRequest(BaseModel):
    records: list[AttendanceMark]


class FaceRecognitionRequest(BaseModel):
    image: str = Field(min_length=1, max_length=4_000_000)


class FaceEnrollmentRequest(FaceRecognitionRequest):
    ic_number: str = Field(min_length=12, max_length=20)


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
