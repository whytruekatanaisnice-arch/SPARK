from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.achievement_certificate import CompetitionCertificateStatus
from app.utils.pajsk_certificate_scoring import (
    CertificatePlacement,
    CompetitionLevel,
    ParticipationType,
)


class CertificateSubmit(BaseModel):
    event_name: str = Field(min_length=3, max_length=255)
    organizer: str = Field(min_length=2, max_length=255)
    awardee_name: str = Field(min_length=2, max_length=255)
    event_date: date
    competition_level: CompetitionLevel
    participation_type: ParticipationType
    placement: CertificatePlacement | None = None
    confirmed_details: bool

    @field_validator("event_name", "organizer", "awardee_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2 or not any(character.isalnum() for character in value):
            raise ValueError("Enter a valid name with at least one letter or number")
        return value

    @model_validator(mode="after")
    def validate_submission(self):
        if self.event_date > date.today():
            raise ValueError("Event date cannot be in the future")
        if not self.confirmed_details:
            raise ValueError("Confirm that every field matches the certificate")
        return self


class CertificateReview(BaseModel):
    status: CompetitionCertificateStatus
    review_note: str | None = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def only_final_review_states(cls, value: CompetitionCertificateStatus) -> CompetitionCertificateStatus:
        if value not in (CompetitionCertificateStatus.APPROVED, CompetitionCertificateStatus.REJECTED):
            raise ValueError("Review status must be approved or rejected")
        return value


class CertificateSubmissionOut(BaseModel):
    id: UUID
    student_id: UUID
    status: CompetitionCertificateStatus
    event_name: str | None
    organizer: str | None
    awardee_name: str | None
    event_date: date | None
    competition_level: str | None
    participation_type: str | None
    placement: str | None
    engagement_score: int | None
    achievement_score: int | None
    score: int | None
    review_note: str | None
    reviewed_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CertificateReviewItem(CertificateSubmissionOut):
    student_name: str
    student_email: str
    ocr_text: str
