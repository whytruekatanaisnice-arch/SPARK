# Email, Certificates & Autosave — Setup Guide

## 1. Enable Gmail sending (App Password)

1. Use a dedicated Gmail account for the school (e.g. `iits.yourschool@gmail.com`) — don't use a personal one.
2. Turn on **2-Step Verification**: Google Account → Security → 2-Step Verification.
3. Open <https://myaccount.google.com/apppasswords>, create an app named `IITS`, and copy the 16-character password.
4. Put this in `iits-backend/.env` (password **without spaces**):

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=True
SMTP_USERNAME=iits.yourschool@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
SMTP_FROM_EMAIL=iits.yourschool@gmail.com
SMTP_FROM_NAME=IITS - Your School Name
APP_LOGIN_URL=https://your-frontend-domain/login.html
```
5. **Restart uvicorn** (`.env` is only read at startup).
6. Create the new database table once: `python seed.py` (it creates missing tables, then skips existing demo data).

**Quick test:** Admin → Users → "Reset password" on a user whose email you can read. If SMTP is wrong, the server log shows `Email send failed ...` and the admin screen still shows the temp password as a fallback.

**Troubleshooting:** `535 Username and Password not accepted` = wrong app password or 2-Step Verification is off. `Connection timed out` = your network blocks port 587.

**Limits:** a free Gmail account sends ~500 emails/day (Workspace ~2,000). Fine for a school pilot; for larger volume switch `SMTP_*` to SendGrid/Mailgun/Brevo — no code change needed.

## 2. What now sends email (and an in-app notification)

| Event | Who is notified |
|---|---|
| Admin creates a user / bulk-imports students | The new user (temporary password) |
| Admin resets a password | That user |
| Coach marks a student **Absent** (first time only — re-saving does not re-send) | The student **and every linked parent** |
| Student/parent submits a certificate | **All active admins** |
| Admin approves/rejects a certificate | The student **and linked parents** |

## 3. Certificate workflow

Student or parent: *Certificates* → pick the missed session (optional) → reason → upload photo/PDF → Submit.
Admin: sidebar shows a **pending count badge** → *Certificates* → Approve/Reject with an optional note.
**Approve** ⇒ the linked attendance record becomes **Excused** and PAJSK points are recalculated automatically.

## 4. Autosave (every 10 seconds)

- **Existing records** (all four profile pages, edit-club / edit-venue / edit-announcement / edit-competition, coach progress notes): changed fields are saved to the server every 10 s. A status line shows *Saving… / All changes saved / Couldn't save — retrying*.
- **New records** (create forms: announcements, clubs, venues, competitions, tasks, notifications, NILAM, certificates): there is no record to save into yet, so the text is kept as a **local draft** every 10 s and restored if the page is closed or refreshed. Cleared after a successful submit.
- Invalid fields (e.g. an empty required name) are not sent until fixed.
