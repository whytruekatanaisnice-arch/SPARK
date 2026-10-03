"""Competition achievements and their PAJSK point values."""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.database import Base


class AchievementRank(Base):
    """Catalog of ranks, e.g. Champion, 1st Runner-up, 2nd Runner-up, Participation."""
    __tablename__ = "achievement_ranks"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    pajsk_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Achievement(Base):
    """A recorded achievement for a student within a club/competition."""
    __tablename__ = "achievements"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clubs.id"), nullable=False, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    rank_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("achievement_ranks.id"), nullable=False)
    competition_name: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str | None] = mapped_column(String(100), nullable=True)  # School / District / State / National
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
