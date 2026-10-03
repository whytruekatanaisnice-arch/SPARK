from uuid import UUID

from pydantic import BaseModel, EmailStr

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
    full_name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    is_active: bool | None = None
    class_name: str | None = None


class UserListItem(UserOut):
    pass


class BulkImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[str]
