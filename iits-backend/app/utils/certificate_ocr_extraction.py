"""Conservative extraction of common PAJSK fields from OCR text."""
import re
from datetime import date, datetime

from app.utils.pajsk_certificate_scoring import CertificatePlacement, CompetitionLevel, ParticipationType

FIELD_PATTERNS = {
    "event_name": re.compile(
        r"^\s*(?:event(?:\s+name)?|competition(?:\s+name)?|program(?:\s+name)?|"
        r"nama\s+program|nama\s+pertandingan|pertandingan|kejohanan)\s*[:：\-–]?\s*(.*)$",
        re.IGNORECASE,
    ),
    "organizer": re.compile(
        r"^\s*(?:organizer|organiser|organized\s+by|organised\s+by|hosted\s+by|"
        r"penganjur|anjuran|dianjurkan\s+oleh)\s*[:：\-–]?\s*(.*)$",
        re.IGNORECASE,
    ),
    "awardee_name": re.compile(
        r"^\s*(?:student\s+name|participant\s+name|awardee|recipient|"
        r"nama\s+murid|nama\s+pelajar|nama\s+peserta|dianugerahkan\s+kepada|"
        r"awarded\s+to|presented\s+to|certify\s+that|certified\s+that|"
        r"disahkan\s+bahawa)\s*[:：\-–]?\s*(.*)$",
        re.IGNORECASE,
    ),
    "event_date": re.compile(
        r"^\s*(?:event\s+date|date\s+of\s+(?:event|competition)|tarikh(?:\s+program)?|"
        r"bertarikh)\s*[:：\-–]?\s*(.*)$",
        re.IGNORECASE,
    ),
    "participation_type": re.compile(
        r"\b(?:engagement|participation|penglibatan)\s*(?:type|category|kategori)?\s*"
        r"(?:type\s*)?(i{1,3}|1|2|3)\b",
        re.IGNORECASE,
    ),
}

DATE_PATTERN = re.compile(
    r"(?<!\d)(\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{4}[./-]\d{1,2}[./-]\d{1,2}|"
    r"\d{1,2}\s+[A-Za-z]+\s+\d{4}|[A-Za-z]+\s+\d{1,2},?\s+\d{4})(?!\d)"
)
MONTHS = {
    "januari": "January",
    "februari": "February",
    "mac": "March",
    "mei": "May",
    "jun": "June",
    "julai": "July",
    "ogos": "August",
    "oktober": "October",
    "disember": "December",
}
PLACEMENT_PATTERNS = (
    (CertificatePlacement.CHAMPION, re.compile(r"(?<!naib\s)\b(?:johan|juara|champion|first\s+place|1st\s+place)\b", re.I)),
    (CertificatePlacement.RUNNER_UP, re.compile(r"\b(?:naib\s+johan|runner[\s-]?up|second\s+place|2nd\s+place)\b", re.I)),
    (CertificatePlacement.THIRD, re.compile(r"\b(?:ketiga|third\s+place|3rd\s+place)\b", re.I)),
    (CertificatePlacement.FOURTH, re.compile(r"\b(?:keempat|fourth\s+place|4th\s+place)\b", re.I)),
    (CertificatePlacement.FIFTH, re.compile(r"\b(?:kelima|fifth\s+place|5th\s+place)\b", re.I)),
)
LEVEL_PATTERNS = (
    (CompetitionLevel.INTERNATIONAL, re.compile(r"\b(?:antarabangsa|international)\b", re.I)),
    (CompetitionLevel.NATIONAL, re.compile(r"\b(?:kebangsaan|national)\b", re.I)),
    (CompetitionLevel.STATE, re.compile(r"\b(?:peringkat\s+negeri|state\s+level)\b", re.I)),
    (CompetitionLevel.DISTRICT, re.compile(r"\b(?:daerah|district|zon|zone)\b", re.I)),
    (CompetitionLevel.SCHOOL, re.compile(r"\b(?:peringkat\s+sekolah|school\s+level)\b", re.I)),
)


def _clean_candidate(value: str) -> str:
    value = re.sub(r"^[\s:：\-–,.]+|[\s:：\-–,.]+$", "", value)
    value = re.sub(r"\s+", " ", value)
    if len(value) < 2 or not any(character.isalnum() for character in value):
        return ""
    return value[:255]


def _labeled_value(lines: list[str], pattern: re.Pattern[str]) -> str | None:
    for index, line in enumerate(lines):
        match = pattern.search(line)
        if not match:
            continue
        value = _clean_candidate(match.group(1))
        if value:
            return value
        for following_line in lines[index + 1:index + 3]:
            value = _clean_candidate(following_line)
            if value:
                return value
    return None


def _marker_following_value(lines: list[str], marker: re.Pattern[str]) -> str | None:
    for index, line in enumerate(lines):
        match = marker.search(line)
        if not match:
            continue
        value = _clean_candidate(match.group(1))
        if value:
            return value
        for following_line in lines[index + 1:index + 3]:
            value = _clean_candidate(following_line)
            if value:
                return value
    return None


def _parse_date(value: str) -> date | None:
    normalized = value.strip().replace(",", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    lowered = normalized.casefold()
    for malay, english in MONTHS.items():
        lowered = re.sub(rf"\b{malay}\b", english, lowered)
    for date_format in (
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
        "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y",
    ):
        try:
            return datetime.strptime(lowered, date_format).date()
        except ValueError:
            continue
    return None


def _extract_event_name(lines: list[str]) -> str | None:
    labeled = _labeled_value(lines, FIELD_PATTERNS["event_name"])
    if labeled:
        return labeled
    return _marker_following_value(
        lines,
        re.compile(r"\b(?:menyertai(?:\s+program)?|participated\s+in|took\s+part\s+in)\b(.*)", re.I),
    )


def _extract_awardee(lines: list[str]) -> str | None:
    labeled = _labeled_value(lines, FIELD_PATTERNS["awardee_name"])
    if labeled:
        return labeled
    return _marker_following_value(
        lines,
        re.compile(r"\b(?:this\s+is\s+to\s+certify\s+that|dengan\s+ini\s+(?:adalah\s+)?disahkan\s+bahawa)\b(.*)", re.I),
    )


def _extract_event_date(lines: list[str]) -> str | None:
    labeled = _labeled_value(lines, FIELD_PATTERNS["event_date"])
    if labeled:
        match = DATE_PATTERN.search(labeled)
        parsed = _parse_date(match.group(1)) if match else None
        if parsed:
            return parsed.isoformat()
    found: set[date] = set()
    for match in DATE_PATTERN.finditer("\n".join(lines)):
        parsed = _parse_date(match.group(1))
        if parsed:
            found.add(parsed)
    return next(iter(found)).isoformat() if len(found) == 1 else None


def extract_certificate_fields(ocr_text: str) -> dict[str, str | None]:
    """Suggest only fields supported by explicit labels or recognizable phrases."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in ocr_text.splitlines()]
    lines = [line for line in lines if line]
    normalized_text = "\n".join(lines)

    event_name = _extract_event_name(lines)
    if event_name and re.fullmatch(
        r"(?:program|pertandingan|kejohanan|competition|event)", event_name, re.I
    ):
        event_name = None

    placement = next(
        (placement.value for placement, pattern in PLACEMENT_PATTERNS if pattern.search(normalized_text)),
        None,
    )
    level = next(
        (level.value for level, pattern in LEVEL_PATTERNS if pattern.search(normalized_text)),
        None,
    )
    participation_match = FIELD_PATTERNS["participation_type"].search(normalized_text)
    participation_type = None
    if participation_match:
        value = participation_match.group(1).casefold()
        participation_type = {"i": "I", "1": "I", "ii": "II", "2": "II", "iii": "III", "3": "III"}[value]
    elif re.search(r"\b(?:secara\s+bersemuka|in[\s-]?person|face[\s-]?to[\s-]?face)\b", normalized_text, re.I):
        participation_type = "I" if placement else "II"
    elif re.search(
        r"\b(?:online|dalam\s+talian)\b.*\b(?:tanpa\s+interaksi|without\s+(?:live\s+)?interaction|penonton|audience|supporter)\b",
        normalized_text,
        re.I,
    ):
        participation_type = ParticipationType.TYPE_III.value

    return {
        "event_name": event_name,
        "organizer": _labeled_value(lines, FIELD_PATTERNS["organizer"]),
        "awardee_name": _extract_awardee(lines),
        "event_date": _extract_event_date(lines),
        "competition_level": level,
        "participation_type": participation_type,
        "placement": placement,
    }
