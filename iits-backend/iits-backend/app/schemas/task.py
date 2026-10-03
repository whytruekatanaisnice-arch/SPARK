from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ORMBase


class TaskCreate(BaseModel):
    club_id: UUID
    title: str
    description: str | None = None
    due_date: datetime | None = None


class TaskOut(ORMBase):
    id: UUID
    club_id: UUID
    title: str
    description: str | None
    due_date: datetime | None


class SubmissionCreate(BaseModel):
    task_id: UUID
    text_content: str | None = None
    file_url: str | None = None


class SubmissionOut(ORMBase):
    id: UUID
    task_id: UUID
    student_id: UUID
    text_content: str | None
    file_url: str | None
    submitted_at: datetime


class FeedbackCreate(BaseModel):
    submission_id: UUID
    comment: str | None = None
    points_awarded: int | None = None


class FeedbackOut(ORMBase):
    id: UUID
    submission_id: UUID
    coach_id: UUID
    comment: str | None
    points_awarded: int | None
