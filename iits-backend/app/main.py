"""FastAPI application entry point — mounts all routers."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    admin, announcements, attendance, auth, clubs, coach, messaging,
    nilam, notifications, parent, reports, student, tasks, uploads,
)

app = FastAPI(
    title=settings.APP_NAME,
    description="Integrated Information & Tracking System for co-curricular clubs, attendance, AJK roles, achievements, NILAM, and PAJSK scoring.",
    version="1.0.0",
)

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

# --- Coach ---
app.include_router(coach.router)
app.include_router(attendance.router)
app.include_router(tasks.coach_router)

# --- Student ---
app.include_router(student.router)
app.include_router(tasks.student_router)
app.include_router(nilam.router)

# --- Parent ---
app.include_router(parent.router)

# --- Shared ---
app.include_router(clubs.router)
app.include_router(announcements.router)
app.include_router(notifications.router)
app.include_router(messaging.router)
app.include_router(uploads.router)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/", tags=["health"])
async def root():
    return {"message": "IITS API is running. See /docs for interactive API documentation."}
