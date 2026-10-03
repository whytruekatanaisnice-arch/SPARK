from uuid import UUID

from pydantic import BaseModel, EmailStr

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
    new_password: str
