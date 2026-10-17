# PAJSK Attendance & Face Registration

    pip install -r requirements.txt
    python app.py          # http://127.0.0.1:5000

First run creates `coaches.json` with default logins: `admin / admin123`, `coach1 / coach123`.
Change them (generate hashes with `werkzeug.security.generate_password_hash`).

- Face photos: `face_db/{IC}_{FULL_NAME}.jpg`
- Log: `attendance_log.csv` (Timestamp, Student_IC, Student_Name, Teacher_Logged_In, PAJSK_Category, Club_Name)
- Camera access needs `localhost` or HTTPS. Set `PAJSK_SECRET` for a stable session key.
- First scan after startup/enrolment is slow while FaceNet512 loads and the index rebuilds.

## SPARK session integration

SPARK uses this service's private `/internal/recognize`, `/internal/students`,
and `/internal/enroll` endpoints. Face registration is performed from Admin →
Users in SPARK; the legacy standalone registration endpoint is disabled.
The private endpoints require `PAJSK_RECOGNITION_TOKEN`. Configure that same
secret as `PAJSK_FACE_SERVICE_TOKEN` in the SPARK backend `.env`. PAJSK loads
that file automatically at startup and uses it as its
`PAJSK_RECOGNITION_TOKEN`, so no separate PowerShell environment variable is
needed. A `PAJSK_RECOGNITION_TOKEN` already set in the process environment
takes precedence. Set `PAJSK_FACE_SERVICE_URL` to this service's base URL in
the same `.env`. SPARK stores session attendance in its database; scans through
the private recognition endpoint do not write rows to this app's CSV log.

## Manual (fallback) attendance
Kiosk → "Manual attendance" (or the link shown when the camera fails). Tick students, choose a reason, save once.
- Roster = `students.csv` (admin imports CSV with IC, Name, Class) + every enrolled face photo.
- Rows go into the same `attendance_log.csv`, same six columns.
- A student already logged today for the same category + club is skipped.
- Each bulk save is also recorded in `manual_entries_audit.csv` (who, when, reason, which ICs).
