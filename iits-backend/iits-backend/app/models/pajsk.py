"""Tunable PAJSK scoring configuration (points per criterion, per year)."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.database import Base


class PajskConfig(Base):
    """
    Key-value config for point weightings, e.g.
      category="attendance", key="present"  -> points=2
      category="attendance", key="excused"  -> points=1
      category="nilam", key="book_logged"   -> points=1
    Looked up per-year so admins can retune without touching code.
    """
    __tablename__ = "pajsk_config"
    __table_args__ = (UniqueConstraint("category", "key", "year", name="uq_pajsk_config_category_key_year"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # attendance | nilam | role | achievement
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
