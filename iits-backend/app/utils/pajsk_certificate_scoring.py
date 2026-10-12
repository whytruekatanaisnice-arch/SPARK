"""PAJSK certificate score matrices transcribed from the supplied KPM table."""
from enum import Enum


class CompetitionLevel(str, Enum):
    INTERNATIONAL = "international"
    NATIONAL = "national"
    STATE = "state"
    DISTRICT = "district"
    SCHOOL = "school"


class ParticipationType(str, Enum):
    TYPE_I = "I"
    TYPE_II = "II"
    TYPE_III = "III"


class CertificatePlacement(str, Enum):
    CHAMPION = "champion"
    RUNNER_UP = "runner_up"
    THIRD = "third"
    FOURTH = "fourth"
    FIFTH = "fifth"


ENGAGEMENT_SCORES: dict[CompetitionLevel, dict[ParticipationType, int]] = {
    CompetitionLevel.INTERNATIONAL: {
        ParticipationType.TYPE_I: 20,
        ParticipationType.TYPE_II: 15,
        ParticipationType.TYPE_III: 10,
    },
    CompetitionLevel.NATIONAL: {
        ParticipationType.TYPE_I: 17,
        ParticipationType.TYPE_II: 12,
        ParticipationType.TYPE_III: 8,
    },
    CompetitionLevel.STATE: {
        ParticipationType.TYPE_I: 14,
        ParticipationType.TYPE_II: 10,
        ParticipationType.TYPE_III: 6,
    },
    CompetitionLevel.DISTRICT: {
        ParticipationType.TYPE_I: 12,
        ParticipationType.TYPE_II: 9,
        ParticipationType.TYPE_III: 5,
    },
    CompetitionLevel.SCHOOL: {
        ParticipationType.TYPE_I: 11,
        ParticipationType.TYPE_II: 8,
        ParticipationType.TYPE_III: 4,
    },
}

ACHIEVEMENT_SCORES: dict[CompetitionLevel, dict[CertificatePlacement, int]] = {
    CompetitionLevel.INTERNATIONAL: {
        CertificatePlacement.CHAMPION: 20,
        CertificatePlacement.RUNNER_UP: 19,
        CertificatePlacement.THIRD: 18,
        CertificatePlacement.FOURTH: 17,
        CertificatePlacement.FIFTH: 16,
    },
    CompetitionLevel.NATIONAL: {
        CertificatePlacement.CHAMPION: 17,
        CertificatePlacement.RUNNER_UP: 16,
        CertificatePlacement.THIRD: 15,
        CertificatePlacement.FOURTH: 14,
        CertificatePlacement.FIFTH: 13,
    },
    CompetitionLevel.STATE: {
        CertificatePlacement.CHAMPION: 14,
        CertificatePlacement.RUNNER_UP: 13,
        CertificatePlacement.THIRD: 12,
        CertificatePlacement.FOURTH: 11,
        CertificatePlacement.FIFTH: 10,
    },
    CompetitionLevel.DISTRICT: {
        CertificatePlacement.CHAMPION: 11,
        CertificatePlacement.RUNNER_UP: 10,
        CertificatePlacement.THIRD: 9,
        CertificatePlacement.FOURTH: 8,
        CertificatePlacement.FIFTH: 7,
    },
    CompetitionLevel.SCHOOL: {
        CertificatePlacement.CHAMPION: 8,
        CertificatePlacement.RUNNER_UP: 7,
        CertificatePlacement.THIRD: 6,
        CertificatePlacement.FOURTH: 5,
        CertificatePlacement.FIFTH: 4,
    },
}


def calculate_certificate_score(
    level: CompetitionLevel,
    participation_type: ParticipationType,
    placement: CertificatePlacement | None,
) -> tuple[int, int, int]:
    engagement_score = ENGAGEMENT_SCORES[level][participation_type]
    achievement_score = ACHIEVEMENT_SCORES[level][placement] if placement else 0
    return engagement_score, achievement_score, engagement_score + achievement_score
