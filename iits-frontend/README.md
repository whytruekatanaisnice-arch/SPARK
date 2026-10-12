# SPARK Frontend

Static frontend for **SPARK (Smart PAJSK & Activity Automation System)**. It uses
HTML, CSS, and browser JavaScript, with no frontend package manager or build
step. The pages call the FastAPI backend in [`../iits-backend/`](../iits-backend/).

## Contents

- [Requirements](#requirements)
- [Project layout](#project-layout)
- [Configure the API URL](#configure-the-api-url)
- [Run locally](#run-locally)
- [Sign in](#sign-in)
- [How the frontend connects to the backend](#how-the-frontend-connects-to-the-backend)
- [Troubleshooting](#troubleshooting)

## Requirements

- A modern browser with JavaScript enabled
- Python 3.11 or later to run the simple local static file server
- The SPARK backend running locally or at a configured API URL

There are no npm dependencies and no compile/build step. For backend
configuration, database setup, and demo data, see
[`../iits-backend/README.md`](../iits-backend/README.md).

## Project layout

```text
iits-frontend/
├── login.html
├── 403.html
├── 404.html
├── admin/                 # Admin pages
├── coach/                 # Coach pages
├── student/               # Student pages
├── parent/                # Parent pages
└── shared/
    ├── announcements.html
    ├── css/styles.css
    └── js/
        ├── api.js          # API requests, auth token, and error handling
        ├── config.js       # Backend API base URL
        ├── shell.js        # Shared page navigation/layout
        ├── toast.js        # Shared notifications
        └── autosave.js     # Shared draft/autosave behavior
```

## Configure the API URL

By default, [`shared/js/config.js`](./shared/js/config.js) points to:

```text
http://localhost:8000
```

That is correct for local development when the backend is running on port
`8000`. To use another backend, edit `window.IITS_API_BASE` in
`shared/js/config.js` to the backend origin, with no trailing `/api` path. For
example:

```js
window.IITS_API_BASE = "https://api.example.com";
```

The backend must allow the frontend's exact origin through its `CORS_ORIGINS`
setting. Configure CORS in the backend; do not put backend secrets or the
Supabase service-role key in frontend files.

## Run locally

Start the backend first. Follow the setup steps in
[`../iits-backend/README.md`](../iits-backend/README.md), including creating
`iits-backend/.env`, seeding the database, and starting Uvicorn.

Then start the frontend static server in a **separate terminal**.

### Windows — PowerShell

```powershell
cd .\iits-frontend
py -3 -m http.server 5500 --bind 127.0.0.1
```

### Windows — Command Prompt

```bat
cd iits-frontend
py -3 -m http.server 5500 --bind 127.0.0.1
```

### macOS

```bash
cd iits-frontend
python3 -m http.server 5500 --bind 127.0.0.1
```

Open this URL in your browser:

<http://localhost:5500/login.html>

Keep the terminal running while using the frontend. Press `Ctrl+C` to stop the
static server. The backend and frontend must both be running for sign-in and
API-backed pages to work.

## Sign in

The backend `seed.py` script creates these local demo accounts:

| Role | Email | Password |
|---|---|---|
| Admin | `admin@iits.demo` | `Admin@123` |
| Coach | `coach@iits.demo` | `Coach@123` |
| Student | `student@iits.demo` | `Student@123` |
| Parent | `parent@iits.demo` | `Parent@123` |

The accounts exist only after the backend has been configured and seeded. They
are for local development only; do not use them in a production deployment.
Their existing `@iits.demo` email addresses are retained for compatibility
with already-seeded development databases.

## How the frontend connects to the backend

- `shared/js/config.js` defines the backend API base URL.
- `shared/js/api.js` attaches the saved bearer token to API requests and
  handles authentication and request errors.
- After successful login, the browser stores the token and user profile in
  `localStorage`, then opens the dashboard for that role.
- The default frontend origin is `http://localhost:5500`. The backend's
  default `CORS_ORIGINS` allows `http://localhost:5500` and
  `http://127.0.0.1:5500`.

Because this is a static site, use the provided local HTTP server rather than
opening `login.html` directly as a `file://` URL. The pages use root-relative
URLs (for example `/shared/css/styles.css`), which need to be served from the
frontend directory.

## Troubleshooting

### Login says the server cannot be reached

Confirm the backend is running at `http://localhost:8000` and that
`shared/js/config.js` points to that URL. Check the backend health endpoint at
<http://localhost:8000/health>.

### Browser shows a CORS error

Use one of the default allowed origins:

- <http://localhost:5500>
- <http://127.0.0.1:5500>

If using a different host or port, add the exact origin to `CORS_ORIGINS` in
`iits-backend/.env` and restart the backend.

### The page has missing styles or pages return 404

Make sure the static server was started from the `iits-frontend` directory and
open `http://localhost:5500/login.html`, not the file directly from disk.

### Demo account login fails

Confirm the backend database is configured and `python seed.py` completed
successfully. The seed script does not overwrite demo data if it detects that
the demo admin already exists.

### A previous login keeps redirecting or appears stale

The frontend stores login state in browser `localStorage`. Sign out from the
application, or clear the site's local storage in browser developer tools,
then sign in again.
