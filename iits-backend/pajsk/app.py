"""PAJSK Attendance & Face Registration System (Flask + DeepFace/FaceNet512)."""
import base64
import csv
import glob
import json
import os
import re
import threading
from datetime import datetime, timedelta
from functools import wraps

import cv2
import numpy as np
from flask import (Flask, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACE_DIR = os.path.join(BASE_DIR, "face_db")
LOG_FILE = os.path.join(BASE_DIR, "attendance_log.csv")
COACH_FILE = os.path.join(BASE_DIR, "coaches.json")
MODEL_NAME = "FaceNet512"
DUPLICATE_WINDOW = timedelta(seconds=60)
CATEGORIES = ["Sukan/Permainan", "Kelab/Persatuan", "Unit Beruniform"]
CSV_HEADER = ["Timestamp", "Student_IC", "Student_Name",
              "Teacher_Logged_In", "PAJSK_Category", "Club_Name"]

os.makedirs(FACE_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("PAJSK_SECRET") or os.urandom(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  MAX_CONTENT_LENGTH=8 * 1024 * 1024)

# DeepFace rebuilds its .pkl index on disk, so serialise all face-db access.
face_lock = threading.Lock()
log_lock = threading.Lock()
recent_checkins = {}  # (ic, category, club) -> datetime of last logged check-in


# --------------------------------------------------------------------------
# Users (JSON file with hashed passwords). Defaults are created on first run.
# --------------------------------------------------------------------------
def load_users():
    if not os.path.exists(COACH_FILE):
        users = {
            "admin": {"hash": generate_password_hash("admin123"), "role": "admin"},
            "coach1": {"hash": generate_password_hash("coach123"), "role": "coach"},
        }
        with open(COACH_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
        print("!! Created coaches.json with DEFAULT passwords (admin/admin123, "
              "coach1/coach123). Change them before real use.")
    with open(COACH_FILE, encoding="utf-8") as f:
        return json.load(f)


def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "user" not in session:
                if request.path.startswith("/api/"):
                    return jsonify(status="error", message="Not logged in"), 401
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                if request.path.startswith("/api/"):
                    return jsonify(status="error", message="Forbidden"), 403
                return redirect(url_for("setup"))
            return fn(*a, **kw)
        return wrapper
    return deco


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def decode_image(data_url):
    """Base64 data URL -> OpenCV BGR array (or None)."""
    if not data_url or "," not in data_url:
        return None
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1], validate=False)
        return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None


def clean_name(name):
    """Keep letters/digits/apostrophe/hyphen; words joined by underscores."""
    name = re.sub(r"[^\w\s'\-]", " ", name or "", flags=re.UNICODE).replace("_", " ")
    return "_".join(name.split())


def parse_identity(path):
    """{IC}_{FULL_NAME}.jpg -> (ic, 'Full Name'). Split on FIRST underscore only."""
    stem = os.path.splitext(os.path.basename(path))[0]
    ic, _, name = stem.partition("_")
    return ic, name.replace("_", " ")


def csv_safe(value):
    """Stop spreadsheet formula injection from free-text fields."""
    value = (value or "").strip()
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


def clear_index_cache():
    for pkl in glob.glob(os.path.join(FACE_DIR, "*.pkl")):
        try:
            os.remove(pkl)
        except OSError:
            pass


def default_threshold():
    try:
        from deepface.modules.verification import find_threshold
        return find_threshold(MODEL_NAME, "cosine")
    except Exception:
        return 0.30  # DeepFace's FaceNet512 cosine threshold


def recently_logged(ic, category, club, now):
    """True if this IC was logged for this session within the last 60 seconds."""
    key = (ic, category, club)
    last = recent_checkins.get(key)
    if last and now - last < DUPLICATE_WINDOW:
        return True
    if last is None and os.path.exists(LOG_FILE):  # e.g. after a server restart
        with open(LOG_FILE, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))[-200:]
        for r in reversed(rows):
            if len(r) == 6 and r[1] == ic and r[4] == category and r[5] == csv_safe(club):
                try:
                    ts = datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                if now - ts < DUPLICATE_WINDOW:
                    return True
                break
    return False


def write_log(ic, name, teacher, category, club, now):
    new_file = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(CSV_HEADER)
        w.writerow([now.strftime("%Y-%m-%d %H:%M:%S"), ic, csv_safe(name),
                    teacher, category, csv_safe(club)])
    recent_checkins[(ic, category, club)] = now


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("setup" if "user" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        handle = request.form.get("username", "").strip().lower()
        user = load_users().get(handle)
        if user and check_password_hash(user["hash"], request.form.get("password", "")):
            session.clear()
            session.update(user=handle, role=user.get("role", "coach"))
            return redirect(url_for("admin" if session["role"] == "admin" else "setup"))
        error = "Username or password is incorrect."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/setup", methods=["GET", "POST"])
@login_required()
def setup():
    error = None
    if request.method == "POST":
        category = request.form.get("category", "")
        club = " ".join(request.form.get("club", "").split())
        if category not in CATEGORIES:
            error = "Choose a co-curriculum category."
        elif not club or len(club) > 80:
            error = "Enter the club or activity name (up to 80 characters)."
        else:
            session["category"], session["club"] = category, club
            return redirect(url_for("kiosk"))
    return render_template("setup.html", categories=CATEGORIES, error=error,
                           user=session["user"], role=session.get("role"),
                           category=session.get("category"), club=session.get("club"))


@app.route("/kiosk")
@login_required()
def kiosk():
    if not session.get("category") or not session.get("club"):
        return redirect(url_for("setup"))
    return render_template("kiosk.html", user=session["user"],
                           category=session["category"], club=session["club"],
                           today=datetime.now().strftime("%A, %d %B %Y"))


@app.route("/admin")
@login_required("admin")
def admin():
    return render_template("admin.html", user=session["user"])


# --------------------------------------------------------------------------
# APIs
# --------------------------------------------------------------------------
@app.route("/api/register", methods=["POST"])
@login_required("admin")
def api_register():
    data = request.get_json(silent=True) or {}
    ic = re.sub(r"[\s\-]", "", str(data.get("ic", "")))  # accept 050412-14-0123
    name = clean_name(str(data.get("name", "")))
    if not re.fullmatch(r"\d{12}", ic):
        return jsonify(status="error", message="IC number must be 12 digits."), 400
    if not name:
        return jsonify(status="error", message="Enter the student's full name."), 400
    img = decode_image(data.get("image"))
    if img is None:
        return jsonify(status="error", message="Could not read the camera image."), 400

    from deepface import DeepFace
    with face_lock:
        try:  # refuse blurry / no-face / multi-face captures up front
            faces = DeepFace.extract_faces(img_path=img, enforce_detection=True)
        except Exception:
            return jsonify(status="error",
                           message="No clear face found. Face the camera in good light."), 422
        if len(faces) > 1:
            return jsonify(status="error",
                           message="More than one face in frame. Only the student should be visible."), 422

        for old in glob.glob(os.path.join(FACE_DIR, f"{ic}_*.jpg")):  # re-enrol replaces
            os.remove(old)
        filename = f"{ic}_{name}.jpg"
        cv2.imwrite(os.path.join(FACE_DIR, filename), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        clear_index_cache()  # force DeepFace to re-index on the next scan
    return jsonify(status="ok", filename=filename, name=name.replace("_", " "), ic=ic)


@app.route("/api/students")
@login_required("admin")
def api_students():
    out = []
    for p in sorted(glob.glob(os.path.join(FACE_DIR, "*.jpg"))):
        ic, name = parse_identity(p)
        out.append({"ic": ic, "name": name})
    return jsonify(students=out)


@app.route("/api/scan", methods=["POST"])
@login_required()
def api_scan():
    if not session.get("category") or not session.get("club"):
        return jsonify(status="error", message="Session not set up"), 400
    data = request.get_json(silent=True) or {}
    try:
        frame = decode_image(data.get("image"))
        if frame is None:
            return jsonify(status="unknown")
        if not glob.glob(os.path.join(FACE_DIR, "*.jpg")):
            return jsonify(status="unknown")

        from deepface import DeepFace
        with face_lock:
            results = DeepFace.find(img_path=frame, db_path=FACE_DIR,
                                    model_name=MODEL_NAME, enforce_detection=True)

        best = None
        for df in results or []:
            if df is None or len(df) == 0:
                continue
            df = df.sort_values("distance")
            row = df.iloc[0]
            limit = float(row["threshold"]) if "threshold" in df.columns else default_threshold()
            if float(row["distance"]) <= limit and (best is None or row["distance"] < best["distance"]):
                best = row
        if best is None:
            return jsonify(status="unknown")

        ic, name = parse_identity(str(best["identity"]))
        if not ic or not name:
            return jsonify(status="unknown")

        now = datetime.now().replace(microsecond=0)
        category, club = session["category"], session["club"]
        with log_lock:
            logged = not recently_logged(ic, category, club, now)
            if logged:
                write_log(ic, name, session["user"], category, club, now)
        return jsonify(status="found", name=name, ic=ic, logged=logged)
    except Exception:
        # No face in frame, empty DB, model hiccup... all treated as unknown.
        return jsonify(status="unknown")


if __name__ == "__main__":
    load_users()
    # getUserMedia works on localhost; use HTTPS for any other host/device.
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
