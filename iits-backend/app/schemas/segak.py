from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SegakRecordInput(BaseModel):
    student_id: UUID
    clear_record: bool = False
    weight_kg: Decimal | None = Field(default=None, gt=0, le=300, max_digits=5, decimal_places=2)
    height_cm: Decimal | None = Field(default=None, gt=0, le=250, max_digits=5, decimal_places=2)
    step_test_recovery_bpm: int | None = Field(default=None, ge=20, le=250)
    push_up_type: Literal["standard", "modified"] | None = None
    push_up_reps: int | None = Field(default=None, ge=0, le=300)
    curl_up_reps: int | None = Field(default=None, ge=0, le=300)
    sit_and_reach_cm: Decimal | None = Field(default=None, ge=-50, le=100, max_digits=5, decimal_places=2)

    @model_validator(mode="after")
    def validate_push_up_pair(self):
        if (self.push_up_type is None) != (self.push_up_reps is None):
            raise ValueError("Choose standard/modified push-ups and enter the repetition count together")
        if self.clear_record and self.has_measurements():
            raise ValueError("A SEGAK row cannot be cleared and edited in the same request")
        return self

    def has_measurements(self) -> bool:
        return any(
            value is not None
            for value in (
                self.weight_kg,
                self.height_cm,
                self.step_test_recovery_bpm,
                self.push_up_reps,
                self.curl_up_reps,
                self.sit_and_reach_cm,
            )
        )


class SegakBulkSave(BaseModel):
    club_id: UUID
    assessment_date: date
    records: list[SegakRecordInput] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_unique_students(self):
        student_ids = [record.student_id for record in self.records]
        if len(student_ids) != len(set(student_ids)):
            raise ValueError("Each student may only appear once per SEGAK bulk save")
        return self


class SegakRecordOut(BaseModel):
    student_id: UUID
    full_name: str
    student_number: str
    class_name: str | None
    weight_kg: Decimal | None
    height_cm: Decimal | None
    bmi: Decimal | None
    step_test_recovery_bpm: int | None
    push_up_type: str | None
    push_up_reps: int | None
    curl_up_reps: int | None
    sit_and_reach_cm: Decimal | None

    model_config = ConfigDict(from_attributes=True)


class SegakBulkSaveOut(BaseModel):
    detail: str
    saved_count: int
    assessment_date: date
