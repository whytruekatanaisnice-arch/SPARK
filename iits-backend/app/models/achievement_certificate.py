"""Student/parent certificate submissions used to verify PAJSK competition scores."""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CompetitionCertificateStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CompetitionCertificate(Base):
    __tablename__ = "competition_certificates"
    __table_args__ = (
        CheckConstraint(
            "status NOT IN ('pending', 'approved') OR "
            "(event_name IS NOT NULL AND event_key IS NOT NULL AND event_date IS NOT NULL "
            "AND organizer IS NOT NULL AND awardee_name IS NOT NULL AND competition_level IS NOT NULL "
            "AND participation_type IS NOT NULL AND engagement_score IS NOT NULL "
            "AND achievement_score IS NOT NULL AND score IS NOT NULL)",
            name="ck_competition_certificate_submitted_fields",
        ),
        Index(
            "uq_competition_certificate_event",
            "student_id",
            "event_date",
            "event_key",
            unique=True,
            postgresql_where=text("status IN ('pending', 'approved')"),
        ),
        Index(
            "uq_competition_certificate_file",
            "student_id",
            "file_sha256",
            unique=True,
            postgresql_where=text("status IN ('pending', 'approved')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[CompetitionCertificateStatus] = mapped_column(
        Enum(
            CompetitionCertificateStatus,
            name="competition_certificate_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=CompetitionCertificateStatus.DRAFT,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    ocr_text: Mapped[str] = mapped_column(Text, nullable=False)

    event_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organizer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    awardee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    competition_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    participation_type: Mapped[str | None] = mapped_column(String(1), nullable=True)
    placement: Mapped[str | None] = mapped_column(String(20), nullable=True)
    engagement_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    achievement_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
