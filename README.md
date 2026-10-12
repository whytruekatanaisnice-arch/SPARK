# SPARK

**Smart PAJSK & Activity Automation System**

SPARK is a web application for managing a school's co-curricular activities.
It supports administrators, coaches, students, and parents with club
management, attendance, student roles, achievements, NILAM reading records,
certificates, notifications, and PAJSK scoring.

This repository contains a static HTML/CSS/JavaScript frontend and a Python
FastAPI backend. The backend uses Supabase PostgreSQL for application data and
Supabase Storage for uploaded files. The `iits-backend` and `iits-frontend`
directory names are retained as the current repository layout.

## Repository layout

```text
SPARK/
├── iits-backend/     # FastAPI API, database models, seed script
├── iits-frontend/    # Static frontend pages and shared browser JavaScript
└── README.md         # Project overview and local quickstart
```

## Requirements

- Python 3.11 or later
- A Supabase project with a PostgreSQL database
- A modern web browser

There is no frontend package manager or build step. For detailed platform
setup, environment variables, Supabase configuration, and troubleshooting,
see the module guides:

- [Backend setup and API guide](./iits-backend/README.md)
- [Frontend setup and run guide](./iits-frontend/README.md)

## Run locally

### 1. Configure and start the backend

Follow the backend guide to create a Supabase project, set up the Python
environment, and configure `iits-backend/.env`. Then, from the repository root,
run these commands in a terminal:

**Windows (PowerShell):**

```powershell
cd .\iits-backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env with your Supabase settings before continuing.
python seed.py
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**macOS:**

```bash
cd iits-backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Supabase settings before continuing.
python seed.py
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Keep this terminal running. The SPARK API is available at
<http://localhost:8000>; its interactive documentation is at
<http://localhost:8000/docs>.

### 2. Start the frontend

Open a second terminal at the repository root and serve the static frontend:

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

Open <http://localhost:5500/login.html> in a browser. Use the local demo
accounts listed in the [backend guide](./iits-backend/README.md). Their
existing `@iits.demo` email addresses are retained for compatibility with
already-seeded development databases. These accounts have known passwords and
must only be used for development.

Both terminals must remain open while you use the application. To stop either
server, press `Ctrl+C` in its terminal.

## Security note

Do not commit `iits-backend/.env` or expose Supabase service-role credentials in
frontend files. The seeded demo accounts and development configuration are
not suitable for production. Review the module guides before deploying.
