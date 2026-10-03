from uuid import UUID

from pydantic import BaseModel


class PajskBreakdown(BaseModel):
    role_points: int
    achievement_points: int
    attendance_points: int
    nilam_points: int
    total: int


class DashboardStats(BaseModel):
    total_students: int
    total_coaches: int
    total_clubs: int
    attendance_today: int
    pending_tasks: int


class LeaderboardEntry(BaseModel):
    club_id: UUID
    club_name: str
    attendance_score: float
    task_score: float
    achievement_score: float
    total_score: float
    rank: int
