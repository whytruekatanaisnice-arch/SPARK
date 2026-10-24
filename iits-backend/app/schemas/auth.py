import re
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMBase


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMBase):
    id: UUID
    email: EmailStr
    full_name: str
    role: str
    phone: str | None = None
    avatar_url: str | None = None
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=12, max_length=72)

    @field_validator("new_password")
    @classmethod
    def validate_strong_password(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        requirements = {
            "an uppercase letter": re.search(r"[A-Z]", value) is not None,
            "a lowercase letter": re.search(r"[a-z]", value) is not None,
            "a number": re.search(r"[0-9]", value) is not None,
            "a symbol": re.search(r"[\x21-\x2F\x3A-\x40\x5B-\x60\x7B-\x7E]", value) is not None,
        }
        missing = [label for label, satisfied in requirements.items() if not satisfied]
        if missing:
            raise ValueError("Password must include " + ", ".join(missing))
        return value
