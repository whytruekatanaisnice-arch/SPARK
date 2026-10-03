"""AJK (Ahli Jawatankuasa) committee roles and their PAJSK point values."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.database import Base


class RoleType(Base):
    """Catalog of AJK positions, e.g. President, Secretary, Treasurer, AJK Biasa."""
    __tablename__ = "role_types"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    pajsk_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class StudentRole(Base):
    """A student's assigned AJK position within a club for a given year."""
    __tablename__ = "student_roles"
    __table_args__ = (UniqueConstraint("club_id", "student_id", "year", name="uq_one_role_per_student_per_club_year"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clubs.id"), nullable=False, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    role_type_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("role_types.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
