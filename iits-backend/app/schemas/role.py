from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ORMBase


class RoleTypeOut(ORMBase):
    id: UUID
    name: str
    pajsk_points: int


class AssignRoleRequest(BaseModel):
    club_id: UUID
    student_id: UUID
    role_type_id: UUID
    year: int


class StudentRoleOut(ORMBase):
    id: UUID
    club_id: UUID
    student_id: UUID
    role_type_id: UUID
    year: int
