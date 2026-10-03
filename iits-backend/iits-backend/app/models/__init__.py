"""
Import all models here so Alembic / Base.metadata can discover every table
with a single `from app.models import *` or `import app.models`.
"""
from app.models.user import User, StudentProfile, CoachProfile, ParentStudentLink, UserRole  # noqa
from app.models.club import Club, Venue, ClubSchedule, ClubMembership, WeekDay  # noqa
from app.models.role import RoleType, StudentRole  # noqa
from app.models.attendance import AttendanceSession, AttendanceRecord, AttendanceStatus  # noqa
from app.models.achievement import AchievementRank, Achievement  # noqa
from app.models.task import Task, Submission, Feedback  # noqa
from app.models.nilam import NilamRecord  # noqa
from app.models.announcement import Announcement  # noqa
from app.models.notification import Notification  # noqa
from app.models.message import Conversation, ConversationParticipant, Message  # noqa
from app.models.pajsk import PajskConfig  # noqa
from app.models.competition import InterClubCompetition  # noqa
from app.models.progress import ProgressNote  # noqa
