"""Shared/generic Pydantic schemas."""
from pydantic import BaseModel, ConfigDict


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str


class Paginated(ORMBase):
    total: int
    page: int
    page_size: int
    items: list
