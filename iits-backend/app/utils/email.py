"""
Outbound email — used to send temporary passwords to newly created/reset users.

If SMTP_HOST isn't configured (e.g. local development), emails are printed to
the server console instead of failing, so the rest of the flow still works.
Sending is synchronous (smtplib has no async API); run via asyncio.to_thread
so it doesn't block the event loop.

Both send_* functions return True/False (never raise) so callers can decide
how to surface a failure (e.g. log it) without breaking the account action.
"""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def _send_sync(to_email: str, subject: str, body: str) -> bool:
    if not settings.SMTP_HOST:
        print(f"\n--- [DEV EMAIL — SMTP not configured in .env] ---\nTo: {to_email}\nSubject: {subject}\n\n{body}\n---------------------------------------------------\n")
        return True  # "sent" in the sense that the dev flow isn't blocked

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001 — a mail failure must never break account creation
        logger.warning("Email send failed to %s: %s", to_email, exc)
        return False


async def send_welcome_email(to_email: str, full_name: str, temp_password: str, role: str) -> bool:
    subject = "Your SPARK account has been created"
    body = (
        f"Hi {full_name},\n\n"
        f"An account for SPARK has been created for you as a {role}.\n\n"
        f"Email: {to_email}\n"
        f"Temporary password: {temp_password}\n\n"
        f"Log in here: {settings.APP_LOGIN_URL}\n"
        f"You'll be able to change your password after logging in.\n\n"
        f"— SPARK"
    )
    return await asyncio.to_thread(_send_sync, to_email, subject, body)


async def send_password_reset_email(to_email: str, full_name: str, temp_password: str) -> bool:
    subject = "Your SPARK password has been reset"
    body = (
        f"Hi {full_name},\n\n"
        f"Your SPARK password has been reset by your school admin.\n\n"
        f"New temporary password: {temp_password}\n\n"
        f"Log in here: {settings.APP_LOGIN_URL}\n"
        f"We recommend changing this password after logging in.\n\n"
        f"— SPARK"
    )
    return await asyncio.to_thread(_send_sync, to_email, subject, body)


async def send_email(to_email: str, subject: str, body: str) -> bool:
    """Generic send, for callers (e.g. notification helpers) that build their own body."""
    return await asyncio.to_thread(_send_sync, to_email, subject, body)


def absence_email_body(recipient_name: str, student_name: str, club_name: str, session_date: str, is_student: bool) -> str:
    who = "You were" if is_student else f"{student_name} was"
    return (
        f"Hi {recipient_name},\n\n"
        f"{who} marked ABSENT from {club_name} on {session_date}.\n\n"
        f"If this absence was for a valid reason (illness, family emergency, etc.), "
        f"a supporting certificate or document can be uploaded for the school's review "
        f"from the Certificates section of the SPARK portal: {settings.APP_LOGIN_URL}\n\n"
        f"— SPARK"
    )


def certificate_submitted_email_body(admin_name: str, student_name: str, club_name: str, reason: str) -> str:
    return (
        f"Hi {admin_name},\n\n"
        f"{student_name} has a certificate awaiting your review (absence from {club_name}).\n\n"
        f"Reason given: {reason}\n\n"
        f"Approve or reject it from the Certificates section: {settings.APP_LOGIN_URL}\n\n"
        f"— SPARK"
    )


def certificate_decision_email_body(recipient_name: str, student_name: str, approved: bool, review_note: str | None, is_student: bool) -> str:
    whose = "Your" if is_student else f"{student_name}'s"
    decision = "APPROVED" if approved else "REJECTED"
    note_line = f"Admin note: {review_note}\n\n" if review_note else ""
    outcome = "The related attendance record has been updated to Excused." if approved else "The absence record remains unchanged."
    return (
        f"Hi {recipient_name},\n\n"
        f"{whose} certificate submission has been {decision}.\n\n"
        f"{note_line}{outcome}\n\n"
        f"View details at: {settings.APP_LOGIN_URL}\n\n"
        f"— SPARK"
    )
