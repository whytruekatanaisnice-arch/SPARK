"""
Seed script: creates demo accounts (admin, coach, student, parent), a sample
club, PAJSK config defaults, role types, and achievement ranks.

Run with:  python seed.py
"""
import asyncio
from datetime import time

from sqlalchemy import select

from app.database import AsyncSessionLocal, engine, Base
from app.models.achievement import AchievementRank
from app.models.club import Club, ClubMembership, ClubSchedule, WeekDay
from app.models.pajsk import PajskConfig
from app.models.role import RoleType
from app.models.user import CoachProfile, ParentStudentLink, StudentProfile, User, UserRole
from app.security import hash_password

CURRENT_YEAR = 2026

DEMO_ACCOUNTS = {
    "admin": {"email": "admin@iits.demo", "password": "Admin@123", "full_name": "Puan Zaharah (Admin)"},
    "coach": {"email": "coach@iits.demo", "password": "Coach@123", "full_name": "Cikgu Aminah"},
    "student": {"email": "student@iits.demo", "password": "Student@123", "full_name": "Ahmad Bin Ismail"},
    "parent": {"email": "parent@iits.demo", "password": "Parent@123", "full_name": "Encik Ismail"},
}

ROLE_TYPES = [
    ("President", 10),
    ("Vice President", 8),
    ("Secretary", 8),
    ("Treasurer", 8),
    ("AJK", 5),
]

ACHIEVEMENT_RANKS = [
    ("Champion", 20),
    ("1st Runner-up", 15),
    ("2nd Runner-up", 10),
    ("Participation", 3),
]

PAJSK_CONFIG_DEFAULTS = [
    ("attendance", "present", 2),
    ("attendance", "late", 1),
    ("attendance", "excused", 1),
    ("attendance", "absent", 0),
    ("nilam", "book_logged", 1),
]


async def main() -> None:
    # Create tables (fine for a demo; use Alembic migrations in production instead).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == DEMO_ACCOUNTS["admin"]["email"]))
        if existing.scalar_one_or_none():
            print("Seed data already exists — skipping.")
            return

        # --- Users ---
        admin = User(email=DEMO_ACCOUNTS["admin"]["email"], full_name=DEMO_ACCOUNTS["admin"]["full_name"],
                     role=UserRole.ADMIN, password_hash=hash_password(DEMO_ACCOUNTS["admin"]["password"]))
        coach = User(email=DEMO_ACCOUNTS["coach"]["email"], full_name=DEMO_ACCOUNTS["coach"]["full_name"],
                     role=UserRole.COACH, password_hash=hash_password(DEMO_ACCOUNTS["coach"]["password"]))
        student = User(email=DEMO_ACCOUNTS["student"]["email"], full_name=DEMO_ACCOUNTS["student"]["full_name"],
                       role=UserRole.STUDENT, password_hash=hash_password(DEMO_ACCOUNTS["student"]["password"]))
        parent = User(email=DEMO_ACCOUNTS["parent"]["email"], full_name=DEMO_ACCOUNTS["parent"]["full_name"],
                      role=UserRole.PARENT, password_hash=hash_password(DEMO_ACCOUNTS["parent"]["password"]))
        db.add_all([admin, coach, student, parent])
        await db.flush()

        db.add(CoachProfile(user_id=coach.id, staff_number="T001", subject="Science"))
        db.add(StudentProfile(user_id=student.id, student_number="STU001", class_name="3 Bestari"))
        db.add(ParentStudentLink(parent_id=parent.id, student_id=student.id, relationship_label="Father"))

        # --- Club ---
        club = Club(name="Robotics Club", category="Club & Society", coach_id=coach.id)
        db.add(club)
        await db.flush()
        db.add(ClubSchedule(club_id=club.id, day_of_week=WeekDay.WED, start_time=time(14, 30), end_time=time(16, 0)))
        db.add(ClubMembership(club_id=club.id, student_id=student.id))

        # --- Role types & achievement ranks ---
        for name, points in ROLE_TYPES:
            db.add(RoleType(name=name, pajsk_points=points))
        for name, points in ACHIEVEMENT_RANKS:
            db.add(AchievementRank(name=name, pajsk_points=points))

        # --- PAJSK config for the current year ---
        for category, key, points in PAJSK_CONFIG_DEFAULTS:
            db.add(PajskConfig(category=category, key=key, points=points, year=CURRENT_YEAR))

        await db.commit()

        print("Seed complete. Demo accounts:")
        for role, info in DEMO_ACCOUNTS.items():
            print(f"  {role:8s} -> {info['email']} / {info['password']}")


if __name__ == "__main__":
    asyncio.run(main())
