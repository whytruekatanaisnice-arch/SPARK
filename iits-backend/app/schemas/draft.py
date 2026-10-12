from pydantic import BaseModel, Field, field_validator


class DraftUpdate(BaseModel):
    data: dict[str, str | bool] = Field(max_length=100)

    @field_validator("data")
    @classmethod
    def validate_draft_fields(cls, data: dict[str, str | bool]) -> dict[str, str | bool]:
        if any(not key or len(key) > 200 for key in data):
            raise ValueError("Draft field keys must be between 1 and 200 characters")
        if any(isinstance(value, str) and len(value) > 5000 for value in data.values()):
            raise ValueError("Draft field values cannot exceed 5000 characters")
        return data
