# SPARK Backend

FastAPI backend for **SPARK (Smart PAJSK & Activity Automation System)**, a
co-curricular management system for clubs, attendance, student roles,
achievements, NILAM reading records, certificates, and PAJSK scoring.

This guide covers backend setup on Windows and macOS, running the API locally,
and connecting it to the static frontend in [`../iits-frontend/`](../iits-frontend/).

## Contents

- [Requirements](#requirements)
- [Project layout](#project-layout)
- [Configure Supabase](#configure-supabase)
- [Install and configure the backend](#install-and-configure-the-backend)
- [Create tables and demo data](#create-tables-and-demo-data)
- [Run the backend](#run-the-backend)
- [Run the full application](#run-the-full-application)
- [Demo accounts](#demo-accounts)
- [API overview](#api-overview)
- [Authentication and frontend behavior](#authentication-and-frontend-behavior)
- [PAJSK scoring](#pajsk-scoring)
- [Bulk student import](#bulk-student-import)
- [Configuration reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [Production notes](#production-notes)

## Requirements

- Python 3.11 or later
- A Supabase project with a PostgreSQL database
- Git, if you are cloning the repository

Install Python from [python.org](https://www.python.org/downloads/) if it is
not already available. On Windows, select the Python Launcher option during
installation so `py -3` is available. Confirm the installed version with
`py -3 --version` on Windows or `python3 --version` on macOS.

For backend-only work, the frontend is not required. To sign in through the
browser, run the frontend as described in
[`iits-frontend/README.md`](../iits-frontend/README.md).

## Project layout

```text
iits-backend/
├── app/
│   ├── main.py          # FastAPI application and registered routers
│   ├── config.py        # Environment-based settings
│   ├── database.py      # Async SQLAlchemy engine and sessions
│   ├── security.py      # Authentication and role checks
│   ├── models/          # SQLAlchemy models
│   ├── schemas/         # Pydantic request/response schemas
│   ├── routers/         # API endpoints
│   └── utils/           # PAJSK, email, and shared helpers
├── migrations/          # Migration-related project files
├── requirements.txt
├── .env.example
├── seed.py              # Creates database tables and demo data
└── sample_students.csv  # Example bulk-import CSV
```

## Configure Supabase

1. Create a project at [supabase.com](https://supabase.com/).
2. In **Project Settings → Database**, copy a PostgreSQL connection string.
   Use a connection option supported by your Supabase project (direct
   connection or session pooler) and set its scheme to
   `postgresql+asyncpg://` for this application. The resulting setting should
   look like:

   ```text
   postgresql+asyncpg://USER:PASSWORD@HOST:PORT/postgres
   ```

   If your database password contains reserved URL characters, URL-encode
   those characters before putting the password in the connection string.
3. In **Project Settings → API**, copy the **Project URL** and the
   **service_role key**. The service-role key is a backend secret: never put it
   in frontend files, commit it, or share it publicly.
4. If you want to test file uploads, create a Storage bucket named
   `submissions`. The current upload endpoint returns a public object URL, so
   the bucket must allow public reads for those returned URLs to work. Do not
   use sensitive files with a public bucket. Private-bucket signed URL support
   is not implemented in this starter.

The database schema is created by `seed.py`. Do not manually create the
application tables first.

## Install and configure the backend

Run these commands from the repository root (`SPARK`). Create and activate a
virtual environment, install dependencies, then create the local environment
file from the example.

### Windows — PowerShell

```powershell
cd .\iits-backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks virtual-environment activation, either use **Command
Prompt** commands below or allow script activation for the current PowerShell
process:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Windows — Command Prompt

```bat
cd iits-backend
py -3 -m venv .venv
.\.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

### macOS

```bash
cd iits-backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `iits-backend/.env` and set at least:

```dotenv
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/postgres
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
JWT_SECRET_KEY=REPLACE_WITH_A_LONG_RANDOM_SECRET
```

To generate a suitable random JWT secret after Python is installed, run
`python -c "import secrets; print(secrets.token_urlsafe(32))"` and copy the
output into `JWT_SECRET_KEY`.

Keep the `.env` file local. Do not commit real credentials. The remaining
settings in `.env.example` have local-development defaults; see
[Configuration reference](#configuration-reference).

## Create tables and demo data

With the virtual environment activated and the working directory set to
`iits-backend`, run:

```bash
python seed.py
```

The script creates the tables using SQLAlchemy `create_all` and inserts demo
users, a Robotics Club, a sample membership and schedule, role types,
achievement ranks, and PAJSK defaults for 2026 (the year currently set in
`seed.py`). If the demo admin already exists, the script reports that seed data
exists and skips inserting it again.

> **Development data only:** Demo users have known passwords. Do not seed
> these accounts into a production environment.

The project does not currently use Alembic migrations for schema changes.
`create_all` is suitable for initial local setup, but it does not manage
ongoing schema evolution; use a reviewed migration process before production
use.

## Run the backend

Start the API from `iits-backend` with the virtual environment activated:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The server will reload when Python files change. Leave this terminal running.

| Purpose | URL |
|---|---|
| API root | <http://localhost:8000/> |
| Health check | <http://localhost:8000/health> |
| Interactive API docs | <http://localhost:8000/docs> |
| Alternative API docs | <http://localhost:8000/redoc> |

To stop the development server, press `Ctrl+C`.

## Run the full application

1. Start the backend using the instructions above.
2. Open a **second terminal** at the repository root.
3. Start the frontend static server:

   **Windows (PowerShell or Command Prompt):**

   ```powershell
   cd .\iits-frontend
   py -3 -m http.server 5500 --bind 127.0.0.1
   ```

   **macOS:**

   ```bash
   cd iits-frontend
   python3 -m http.server 5500 --bind 127.0.0.1
   ```

4. Visit <http://localhost:5500/login.html> and use one of the demo accounts
   below.

The frontend defaults to `http://localhost:8000` for its API and the backend
allows the frontend origins `http://localhost:5500` and
`http://127.0.0.1:5500`. Keep the browser URL and these origins consistent. If
you use another frontend host or port, update `CORS_ORIGINS` in the backend
`.env` to include the exact frontend origin, then restart the backend.

See [`iits-frontend/README.md`](../iits-frontend/README.md) for frontend-only
instructions and API URL configuration.

## Demo accounts

| Role | Email | Password |
|---|---|---|
| Admin | `admin@iits.demo` | `Admin@123` |
| Coach | `coach@iits.demo` | `Coach@123` |
| Student | `student@iits.demo` | `Student@123` |
| Parent | `parent@iits.demo` | `Parent@123` |

These accounts are for local development only. Their `@iits.demo` email
addresses are retained for compatibility with existing development databases.
The seeded student is linked to the seeded parent and is a member of the sample
Robotics Club.

## API overview

The backend exposes interactive request and response documentation at
<http://localhost:8000/docs>. The main API areas are:

| API area | Typical users | Purpose |
|---|---|---|
| `/api/auth` | All roles | Login, logout, current user, and password actions. |
| `/api/admin` and `/api/admin/reports` | Admin | User and school data management, dashboards, and reports. |
| `/api/coach` and `/api/coach/attendance` | Coaches (some actions also allow admins) | Club activity, attendance, student progress, roles, and tasks. |
| `/api/student` and `/api/student/nilam` | Students | Student dashboard, activities, tasks, reading records, and profile. |
| `/api/parent` | Parents | Linked children, attendance, certificates, and parent views. |
| `/api/clubs`, `/api/announcements`, `/api/notifications`, `/api/messaging`, `/api/uploads` | Authenticated users, depending on endpoint | Shared club, announcement, notification, messaging, and upload functionality. |
| `/api/student/certificates`, `/api/admin/certificates` | Students / admins | Submit and review attendance certificates. |

Some routers have role-specific access checks. Use `/docs` to see the current
endpoint list, required authentication, and exact request/response schemas.

## Authentication and frontend behavior

1. The frontend sends `POST /api/auth/login` with an email and password.
2. On success, the API returns an access token and user profile.
3. The frontend stores the token and profile in browser `localStorage` and
   sends the token on subsequent requests as
   `Authorization: Bearer <access_token>`.
4. The frontend routes the user to the dashboard for their role. A `401`
   response clears the saved login state and redirects to the login page.

The existing `IITS` JavaScript namespace in the frontend is an internal
implementation identifier, not the product's displayed name. Do not store or
expose backend secrets in the frontend. For production,
consider the security implications of storing authentication tokens in
browser `localStorage`.

## PAJSK scoring

PAJSK totals and breakdowns are calculated by the backend and saved to student
profiles. Attendance, role assignments, achievements, and NILAM records can
trigger recalculation automatically. Scoring values are stored in the
`pajsk_config` table by category, key, and year; the seed script inserts
development defaults for 2026, as configured in `seed.py`.

## Bulk student import

The admin bulk-import API accepts a multipart CSV upload. The expected columns
are shown in [`sample_students.csv`](./sample_students.csv):

```csv
full_name,email,student_number,class_name,ic_number
Ahmad Bin Ismail,ahmad.ismail@student.school.edu.my,STU001,3 Bestari,050101010001
```

Rows whose email already exists are skipped rather than overwritten. New
students receive a generated temporary password. Review the current endpoint
behavior in `/docs` before using bulk import operationally; do not distribute
credentials in an insecure way.

## Configuration reference

| Variable | Required | Purpose |
|---|---:|---|
| `DATABASE_URL` | Yes | Async PostgreSQL connection string using the `postgresql+asyncpg` scheme. |
| `SUPABASE_URL` | Yes | Supabase project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Backend-only key used for Supabase Storage uploads. |
| `SUPABASE_STORAGE_BUCKET` | No | Upload bucket name; defaults to `submissions`. |
| `JWT_SECRET_KEY` | Yes | Secret used to sign authentication tokens. Use a unique, long random value. |
| `JWT_ALGORITHM` | No | JWT signing algorithm; defaults to `HS256`. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | Token lifetime in minutes; defaults to `720` (12 hours). |
| `CORS_ORIGINS` | No | Comma-separated allowed frontend origins; defaults to localhost ports 5500. |
| `DEBUG` | No | Enables SQLAlchemy SQL echo when true; defaults to `True`. |
| `SMTP_HOST` | No | SMTP host. Leave blank for local development; emails are printed to the backend console instead of being sent. |
| `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` | No | SMTP connection settings when `SMTP_HOST` is configured. |
| `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME` | No | Sender identity for outbound mail. |
| `SMTP_USE_TLS` | No | SMTP TLS setting; defaults to `True`. |
| `APP_LOGIN_URL` | No | Login link included in emails; defaults to `http://localhost:5500/login.html`. |

For local development, keep `SMTP_HOST` blank. The sample `.env.example` is
configured this way, so outgoing messages are written to the backend console.
To configure real email delivery, set `SMTP_HOST` and provide valid SMTP
settings; see [`EMAIL_AND_WORKFLOWS.md`](./EMAIL_AND_WORKFLOWS.md). Restart
the backend after changing `.env`.

## Troubleshooting

### `ValidationError` or missing setting when starting the API

Check that `iits-backend/.env` exists, contains `DATABASE_URL`,
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `JWT_SECRET_KEY`, and has no
unquoted placeholder text or accidental spaces around values.

### Database connection fails during seeding or startup

- Confirm the Supabase project is active and the database host, port, username,
  password, and database name are correct.
- Confirm the connection string uses `postgresql+asyncpg://`.
- If the direct connection is unreachable from your network, try the
  connection option recommended by Supabase for your environment (for example,
  its session pooler).
- URL-encode reserved characters in the database password.

### Browser reports a CORS error

The frontend origin must exactly match an entry in `CORS_ORIGINS`. For example,
`http://localhost:5500` and `http://127.0.0.1:5500` are different origins.
Update the backend `.env` and restart Uvicorn.

### Browser cannot reach the API

Confirm both development servers are running. The frontend API URL defaults
to `http://localhost:8000`; see
[`iits-frontend/README.md`](../iits-frontend/README.md) if your backend uses a
different address.

### File upload fails

Confirm the `submissions` bucket exists, `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY` are valid, and the uploaded file is an allowed
image, PDF, or video file no larger than 25 MB. The current API returns public
object URLs, so the bucket must permit public reads for those links to work.

## Production notes

- Do not deploy the demo accounts or development credentials.
- Set `DEBUG=False`, use a strong unique `JWT_SECRET_KEY`, and configure
  production CORS origins explicitly.
- Store Supabase and SMTP secrets in the deployment platform's secret manager,
  not in source control or frontend files.
- Review database access and Supabase Storage policies for your deployment.
  The API also performs authentication and role checks; database policies are
  not a substitute for application authorization.
- Add a proper database migration workflow before making production schema
  changes. The development seed script uses `create_all`.
- Configure the deployment start command with the platform-provided port, for
  example `uvicorn app.main:app --host 0.0.0.0 --port $PORT` where supported.
- Review and follow [`EMAIL_AND_WORKFLOWS.md`](./EMAIL_AND_WORKFLOWS.md) before
  enabling outbound email.
