from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.schemas.common import ORMBase


class CertificateCreate(BaseModel):
    reason: str
    file_url: str | None = None
    attendance_record_id: UUID | None = None


class CertificateReview(BaseModel):
    status: str  # "approved" | "rejected"
    review_note: str | None = None


class CertificateOut(ORMBase):
    id: UUID
    student_id: UUID
    submitted_by: UUID
    attendance_record_id: UUID | None
    reason: str
    file_url: str | None
    status: str
    review_note: str | None
    reviewed_at: datetime | None
    created_at: datetime

    @field_validator("status", mode="before")
    @classmethod
    def _enum_to_value(cls, v):
        return getattr(v, "value", v)


class CertificateAdminOut(CertificateOut):
    student_name: str | None = None
    student_number: str | None = None
    submitted_by_name: str | None = None
    club_name: str | None = None
    session_date: str | None = None
