"""
Environment configuration for IITS backend.
Loaded once as a singleton `settings` object.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "IITS - Integrated Information & Tracking System"
    ENV: str = "development"
    DEBUG: bool = True

    # --- Database (Supabase Postgres) ---
    # Use the asyncpg-compatible URL, e.g.
    # postgresql+asyncpg://postgres:<password>@<host>:5432/postgres
    DATABASE_URL: str

    # --- Supabase (for Storage) ---
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_STORAGE_BUCKET: str = "submissions"

    # --- Auth / JWT ---
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 hours

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:5500,http://127.0.0.1:5500"

    # --- Outbound email (temp passwords on account creation / reset) ---
    # When SMTP_ENABLED is False (the default), emails are logged instead of
    # sent — lets you develop locally without real SMTP credentials.
    SMTP_ENABLED: bool = False
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "no-reply@iits.local"
    SMTP_FROM_NAME: str = "IITS School System"
    SMTP_USE_TLS: bool = True
    FRONTEND_LOGIN_URL: str = "http://localhost:5500/login.html"

    # --- Outbound email (temporary passwords, notifications) ---
    # If SMTP_HOST is left blank, emails are printed to the server console instead of sent —
    # handy for local development without a real mail provider.
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True
    SMTP_FROM_EMAIL: str = "no-reply@iits.local"
    SMTP_FROM_NAME: str = "IITS"
    APP_LOGIN_URL: str = "http://localhost:5500/login.html"

    # --- Pagination ---
    DEFAULT_PAGE_SIZE: int = 25
    MAX_PAGE_SIZE: int = 200

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
