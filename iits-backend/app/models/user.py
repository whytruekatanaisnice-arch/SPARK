"""User accounts for all 4 roles: admin, coach, student, parent."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    COACH = "coach"
    STUDENT = "student"
    PARENT = "parent"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Role-specific profile info lives in these one-to-one tables
    student_profile: Mapped["StudentProfile"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    coach_profile: Mapped["CoachProfile"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class StudentProfile(Base):
    """
    Extra fields specific to students, incl. PAJSK running total.
    Uses the "shared primary key" one-to-one pattern: user_id is both this
    table's PK and a FK into users.id (a student profile can't exist without
    its user, and a user can't have more than one student profile).
    """
    __tablename__ = "student_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    student_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    class_name: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "3 Bestari"
    ic_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pajsk_points: Mapped[int] = mapped_column(default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="student_profile")


class CoachProfile(Base):
    """Extra fields specific to coaches/teachers (shared primary key with users)."""
    __tablename__ = "coach_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    staff_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(100), nullable=True)

    user: Mapped["User"] = relationship(back_populates="coach_profile")


class ParentStudentLink(Base):
    """Many-to-many: a parent can have multiple children; a student can (rarely) have multiple guardians."""
    __tablename__ = "parent_student_links"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    relationship_label: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "Mother", "Father", "Guardian"
