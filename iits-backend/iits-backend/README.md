# IITS — Integrated Information & Tracking System (Backend)

FastAPI backend for a Malaysian secondary school's co-curricular management system:
clubs, mobile attendance, AJK role assignment, competition achievements, NILAM
reading records, and **automatic PAJSK scoring**.

> This is the **backend** module. Frontend (plain HTML/CSS/JS pages) is a separate
> deliverable — see the main implementation prompt for its page list and design notes.

## 1. Tech stack

- **FastAPI** (Python 3.11+), async throughout
- **PostgreSQL via Supabase**, SQLAlchemy 2.0 async ORM + asyncpg driver
- **Pydantic v2** for request/response validation
- **JWT** auth (PyJWT) with bcrypt password hashing
- **Supabase Storage** for file uploads (task submissions)

## 2. Project structure

```
iits-backend/
├── app/
│   ├── main.py            # FastAPI app entry — mounts all routers
│   ├── config.py           # Settings loaded from .env
│   ├── database.py         # Async engine + session factory
│   ├── security.py         # JWT, password hashing, RBAC dependencies
│   ├── models/              # SQLAlchemy ORM models (one file per domain)
│   ├── schemas/              # Pydantic request/response models
│   ├── routers/              # API routes, grouped by role/domain
│   └── utils/
│       ├── pa_jsK.py         # PAJSK auto-scoring logic
│       └── pagination.py
├── requirements.txt
├── .env.example
├── seed.py                 # Creates demo admin/coach/student/parent + sample data
└── sample_students.csv     # Template for bulk student import
```

## 3. Setup

### 3.1 Create a Supabase project

1. Go to [supabase.com](https://supabase.com) and create a new project.
2. Under **Project Settings → Database**, copy the connection string. Convert it to
   the async form (Supabase gives you `postgresql://...`; use `postgresql+asyncpg://...`).
3. Under **Project Settings → API**, copy the **Project URL** and the
   **service_role key** (not the anon key — the backend needs elevated access to
   write to Storage on the user's behalf).
4. Under **Storage**, create a bucket named `submissions` (or change
   `SUPABASE_STORAGE_BUCKET` in `.env`). Set it to public if you want submitted
   files to be viewable via a plain URL, or keep it private and generate signed
   URLs instead (not implemented in the starter — see `app/routers/uploads.py`).
5. Enable **Row Level Security (RLS)** on every table once you've created them
   via `seed.py` / your migration tool of choice, and add policies restricting
   each table to the appropriate role. RLS is a database-level safety net in
   addition to (not a replacement for) the RBAC checks already enforced in
   `app/security.py`.

### 3.2 Local environment

```bash
cd iits-backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env with your Supabase DATABASE_URL, SUPABASE_URL,
# SUPABASE_SERVICE_ROLE_KEY, and a random JWT_SECRET_KEY
```

### 3.3 Create tables & seed demo data

```bash
python seed.py
```

This creates all tables (via `Base.metadata.create_all` — fine for getting
started; switch to Alembic migrations before running this in production) and
inserts:

| Role    | Email              | Password    |
|---------|--------------------|-------------|
| Admin   | admin@iits.demo    | Admin@123   |
| Coach   | coach@iits.demo    | Coach@123   |
| Student | student@iits.demo  | Student@123 |
| Parent  | parent@iits.demo   | Parent@123  |

It also seeds AJK role types, achievement ranks, one sample club (Robotics Club,
with the demo student as a member), and PAJSK point config for the current year.

### 3.4 Run the dev server

```bash
uvicorn app.main:app --reload
```

API docs (Swagger UI, auto-generated): **http://localhost:8000/docs**
Health check: **http://localhost:8000/health**

## 4. Authentication flow

1. `POST /api/auth/login` with `{ email, password }` → returns `{ access_token, user }`.
2. Frontend stores the token (e.g. in `localStorage`).
3. Every subsequent request sends `Authorization: Bearer <access_token>`.
4. `GET /api/auth/me` returns the current user's profile.
5. On a `401` response, the frontend should clear the stored token and redirect to `login.html`.

## 5. PAJSK auto-scoring

`app/utils/pa_jsK.py` computes each student's PAJSK breakdown on demand
(`calculate_pa_jsK`) and persists the total onto `student_profiles.pajsk_points`
(`recalculate_and_store`). It is called automatically — **no manual sync step
anywhere in the frontend** — whenever:

- attendance is bulk-marked (`POST /api/coach/attendance/sessions/{id}/records`)
- an AJK role is assigned or removed (`POST /api/coach/roles/assign`, `DELETE /api/coach/roles/{id}`)
- an achievement is recorded (`POST /api/coach/achievements`)
- a NILAM book is logged (`POST /api/student/nilam`)

All point weightings live in the `pajsk_config` table (category/key/year →
points), so an admin can retune scoring for a new academic year without any
code changes — just insert/update rows in that table (a small
admin UI for this table is a natural next addition to `admin/reports.html`).

## 6. Key API groups

| Prefix                  | Who               | Covers |
|--------------------------|-------------------|--------|
| `/api/auth`              | Everyone          | Login, logout, profile, password change |
| `/api/admin`             | Admin only        | Users, bulk import, clubs, venues, announcements, dashboard, gamification |
| `/api/admin/reports`     | Admin only        | PAJSK CSV/Excel export |
| `/api/coach`             | Coach/Admin       | Attendance, AJK roles, progress notes, achievements, tasks, notifications |
| `/api/student`           | Student only      | My clubs/schedule/role, tasks, submissions, PAJSK, NILAM, profile |
| `/api/parent`            | Parent only       | Children list, attendance, feedback, PAJSK standing, notifications |
| `/api/clubs`, `/api/announcements`, `/api/notifications`, `/api/messaging`, `/api/uploads` | Shared | Read-mostly endpoints usable by any authenticated role |

Full request/response schemas are documented interactively at `/docs`.

## 7. Deployment notes

- **Backend**: deploy to Render or Railway.
  - Set the same environment variables from `.env` in the platform's dashboard.
  - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
  - Run `python seed.py` once (via a one-off shell/job) against the production
    database if you want the same demo accounts there — otherwise create real
    accounts through `/api/admin/users`.
- **Frontend**: deploy the static HTML/CSS/JS pages to Netlify or Vercel, and
  point their `api.js` base URL at the deployed backend's origin. Add that
  origin to `CORS_ORIGINS` in the backend's `.env`.
- **File storage**: no extra deployment step — Supabase Storage is already
  cloud-hosted; just make sure `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` are
  set in whichever environment is running the backend.

## 8. Bulk student import

`POST /api/admin/users/bulk-import` accepts a multipart file upload with a CSV
in this format (see `sample_students.csv`):

```csv
full_name,email,student_number,class_name,ic_number
Ahmad Bin Ismail,ahmad.ismail@student.school.edu.my,STU001,3 Bestari,050101010001
```

Rows with an email that already exists are skipped (not overwritten); each new
student gets a random temporary password (not returned in the response body in
this starter — wire up an email/SMS step in production, or extend the endpoint
to return them for manual distribution in a controlled setting).

## 9. What's intentionally left for you to extend

- Alembic migrations (schema currently created via `create_all` in `seed.py`)
- Signed/expiring URLs for private Supabase Storage buckets
- A small admin screen for editing `pajsk_config` rows directly
- Push notification delivery (the `notifications` table stores in-app
  notifications; wiring these to actual push/SMS is out of scope here)
- Rate limiting / audit logging for admin actions
