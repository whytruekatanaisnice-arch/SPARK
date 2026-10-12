from pydantic import BaseModel


class ProfileUpdate(BaseModel):
    """Generic self-service profile fields any role may edit (used by autosave)."""
    full_name: str | None = None
    phone: str | None = None
