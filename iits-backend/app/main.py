"""FastAPI application entry point — mounts all routers."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import engine
from app.demo_store import set_fallback_active
from app.routers import (
    achievement_certificates, admin, announcements, attendance, auth, certificates,
    clubs, coach, drafts, messaging, nilam, notifications, parent, reports, segak,
    student, tasks, uploads,
)

app = FastAPI(
    title=settings.APP_NAME,
    description="Smart PAJSK & Activity Automation System for co-curricular clubs, attendance, AJK roles, achievements, NILAM, and PAJSK scoring.",
    version="1.0.0",
)
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Auth ---
app.include_router(auth.router)

# --- Admin ---
app.include_router(admin.router)
app.include_router(clubs.admin_router)
app.include_router(announcements.admin_router)
app.include_router(reports.router)
app.include_router(certificates.admin_router)
app.include_router(achievement_certificates.review_router)

# --- Coach ---
app.include_router(coach.router)
app.include_router(attendance.router)
app.include_router(tasks.coach_router)
app.include_router(segak.router)

# --- Student ---
app.include_router(student.router)
app.include_router(tasks.student_router)
app.include_router(nilam.router)
app.include_router(certificates.student_router)
app.include_router(achievement_certificates.student_router)

# --- Parent ---
app.include_router(parent.router)
app.include_router(certificates.parent_router)
app.include_router(achievement_certificates.parent_router)

# --- Shared ---
app.include_router(clubs.router)
app.include_router(announcements.router)
app.include_router(notifications.router)
app.include_router(messaging.router)
app.include_router(uploads.router)
app.include_router(achievement_certificates.scoring_router)
app.include_router(drafts.router)


@app.on_event("startup")
async def check_database_connection():
    if not settings.DEMO_FALLBACK_ENABLED:
        set_fallback_active(False)
        return

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        set_fallback_active(True)
        logger.warning(
            "Supabase database is unavailable; using local JSON demo data: %s",
            exc,
        )
    else:
        set_fallback_active(False)
        logger.info("Supabase database is available; using the configured database.")


@app.get("/health", tags=["health"])
async def health_check():
    from app import demo_store

    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "demo_fallback_active": demo_store.is_enabled(),
    }


@app.get("/", tags=["health"])
async def root():
    return {"message": "SPARK API is running. See /docs for interactive API documentation."}
