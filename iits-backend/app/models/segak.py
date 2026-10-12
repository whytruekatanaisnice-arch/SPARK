"""SEGAK assessment records collected by coaches."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SegakAssessment(Base):
    __tablename__ = "segak_assessments"
    __table_args__ = (
        UniqueConstraint("student_id", "assessment_date", name="uq_segak_student_assessment_date"),
        CheckConstraint("weight_kg IS NULL OR (weight_kg > 0 AND weight_kg <= 300)", name="ck_segak_weight_range"),
        CheckConstraint("height_cm IS NULL OR (height_cm > 0 AND height_cm <= 250)", name="ck_segak_height_range"),
        CheckConstraint("bmi IS NULL OR bmi > 0", name="ck_segak_bmi_positive"),
        CheckConstraint(
            "step_test_recovery_bpm IS NULL OR step_test_recovery_bpm BETWEEN 20 AND 250",
            name="ck_segak_step_test_range",
        ),
        CheckConstraint(
            "push_up_type IS NULL OR push_up_type IN ('standard', 'modified')",
            name="ck_segak_push_up_type",
        ),
        CheckConstraint(
            "(push_up_type IS NULL AND push_up_reps IS NULL) OR "
            "(push_up_type IS NOT NULL AND push_up_reps IS NOT NULL)",
            name="ck_segak_push_up_pair",
        ),
        CheckConstraint(
            "push_up_reps IS NULL OR push_up_reps BETWEEN 0 AND 300",
            name="ck_segak_push_up_reps_range",
        ),
        CheckConstraint(
            "curl_up_reps IS NULL OR curl_up_reps BETWEEN 0 AND 300",
            name="ck_segak_curl_up_reps_range",
        ),
        CheckConstraint(
            "sit_and_reach_cm IS NULL OR sit_and_reach_cm BETWEEN -50 AND 100",
            name="ck_segak_sit_and_reach_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    assessed_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    assessment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    bmi: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    step_test_recovery_bpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    push_up_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    push_up_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    curl_up_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sit_and_reach_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
