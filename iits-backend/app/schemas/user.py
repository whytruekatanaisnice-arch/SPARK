from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.auth import UserOut


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    role: str  # admin | coach | student | parent
    phone: str | None = None
    password: str | None = None  # if omitted, a random temp password is generated

    # Student-only fields
    student_number: str | None = None
    class_name: str | None = None
    ic_number: str | None = None

    # Coach-only fields
    staff_number: str | None = None
    subject: str | None = None

    # Parent-only field: link to existing student(s) by student_number
    child_student_numbers: list[str] | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    student_number: str | None = Field(default=None, min_length=1, max_length=50)
    class_name: str | None = Field(default=None, max_length=50)
    ic_number: str | None = Field(default=None, max_length=20)
    staff_number: str | None = Field(default=None, max_length=50)
    subject: str | None = Field(default=None, max_length=100)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Full name cannot be blank")
        return value

    @field_validator("phone", "student_number", "class_name", "ic_number", "staff_number", "subject")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        return value


class UserListItem(UserOut):
    student_number: str | None = None
    class_name: str | None = None
    ic_number: str | None = None
    staff_number: str | None = None
    subject: str | None = None


class BulkImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[str]
