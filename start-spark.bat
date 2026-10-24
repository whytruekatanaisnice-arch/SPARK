@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND=%ROOT%iits-backend"
set "FRONTEND=%ROOT%iits-frontend"
set "BACKEND_PYTHON=%BACKEND%\.venv\Scripts\python.exe"
set "PAJSK_PYTHON=%BACKEND_PYTHON%"

if /i "%~1"=="api" goto run_api
if /i "%~1"=="pajsk" goto run_pajsk
if /i "%~1"=="frontend" goto run_frontend

if not exist "%BACKEND%\.env" (
    echo Missing iits-backend\.env
    echo Copy .env.example to .env, configure Supabase and the face-service token, then retry.
    exit /b 1
)

if not exist "%BACKEND_PYTHON%" (
    echo Missing iits-backend\.venv\Scripts\python.exe
    echo Create the backend environment and install iits-backend\requirements.txt first.
    exit /b 1
)

if exist "%BACKEND%\pajsk\.venv\Scripts\python.exe" (
    set "PAJSK_PYTHON=%BACKEND%\pajsk\.venv\Scripts\python.exe"
)

"%BACKEND_PYTHON%" -c "import importlib.util,sys; names=('uvicorn','fastapi','sqlalchemy','asyncpg','pydantic','pydantic_settings','jwt','bcrypt','multipart','httpx','openpyxl','email_validator'); missing=[name for name in names if importlib.util.find_spec(name) is None]; print('Missing backend packages: '+', '.join(missing)) if missing else None; sys.exit(bool(missing))"
if errorlevel 1 (
    echo Install iits-backend\requirements.txt in the backend environment.
    exit /b 1
)

"%PAJSK_PYTHON%" -c "import importlib.util,sys; names=('flask','deepface','cv2','numpy','dotenv','PIL','retinaface'); missing=[name for name in names if importlib.util.find_spec(name) is None]; print('Missing PAJSK packages: '+', '.join(missing)) if missing else None; sys.exit(bool(missing))"
if errorlevel 1 (
    echo Install iits-backend\pajsk\requirements.txt in the selected PAJSK environment.
    exit /b 1
)

if /i "%~1"=="--check" (
    echo Startup prerequisites are available.
    exit /b 0
)

echo Starting SPARK API, PAJSK face recognition, and frontend...
start "SPARK API - 8000" "%ComSpec%" /k ""%~f0" api"
start "PAJSK Face Service - 5000" "%ComSpec%" /k ""%~f0" pajsk"
start "SPARK Frontend - 5500" "%ComSpec%" /k ""%~f0" frontend"
timeout /t 2 /nobreak >nul
start "" "http://localhost:5500/login.html"
exit /b 0

:run_api
cd /d "%BACKEND%"
"%BACKEND_PYTHON%" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
exit /b %errorlevel%

:run_pajsk
cd /d "%BACKEND%"
"%PAJSK_PYTHON%" .\pajsk\app.py
exit /b %errorlevel%

:run_frontend
cd /d "%FRONTEND%"
"%BACKEND_PYTHON%" -m http.server 5500 --bind 127.0.0.1
exit /b %errorlevel%
