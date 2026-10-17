"""PAJSK Attendance & Face Registration System (Flask + DeepFace/FaceNet512)."""
import base64
import csv
import glob
import hmac
import json
import os
import re
import threading
from datetime import datetime, timedelta
from functools import wraps

import cv2
import numpy as np
from dotenv import load_dotenv
from flask import (Flask, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, "..", ".env"))
if not os.environ.get("PAJSK_RECOGNITION_TOKEN"):
    face_service_token = os.environ.get("PAJSK_FACE_SERVICE_TOKEN")
    if face_service_token:
        os.environ["PAJSK_RECOGNITION_TOKEN"] = face_service_token
FACE_DIR = os.path.join(BASE_DIR, "face_db")
LOG_FILE = os.path.join(BASE_DIR, "attendance_log.csv")
COACH_FILE = os.path.join(BASE_DIR, "coaches.json")
ROSTER_FILE = os.path.join(BASE_DIR, "students.csv")        # IC,Name,Class (optional import)
MANUAL_AUDIT_FILE = os.path.join(BASE_DIR, "manual_entries_audit.csv")
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


def find_face_identity(frame):
    """Return the closest enrolled identity only when it passes FaceNet512's threshold."""
    if not glob.glob(os.path.join(FACE_DIR, "*.jpg")):
        return None

    from deepface import DeepFace

    with face_lock:
        results = DeepFace.find(img_path=frame, db_path=FACE_DIR,
                                model_name=MODEL_NAME, enforce_detection=True)

    best = None
    for df in results or []:
        if df is None or len(df) == 0:
            continue
        row = df.sort_values("distance").iloc[0]
        limit = float(row["threshold"]) if "threshold" in df.columns else default_threshold()
        if float(row["distance"]) <= limit and (best is None or row["distance"] < best["distance"]):
            best = row
    if best is None:
        return None

    ic, name = parse_identity(str(best["identity"]))
    if not ic or not name:
        return None
    return ic, name


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
    return redirect("http://localhost:5500/admin/users.html")


# --------------------------------------------------------------------------
# APIs
# --------------------------------------------------------------------------
@app.route("/api/register", methods=["POST"])
@login_required("admin")
def api_register():
    return jsonify(status="error", message="Enroll students from the SPARK admin portal."), 410


@app.route("/api/students")
@login_required("admin")
def api_students():
    return jsonify(status="error", message="Manage face enrollment from the SPARK admin portal."), 410


def require_spark_service_token():
    service_token = os.environ.get("PAJSK_RECOGNITION_TOKEN", "")
    authorization = request.headers.get("Authorization", "")
    supplied_token = authorization.removeprefix("Bearer ")
    if not service_token:
        return jsonify(status="error", message="Recognition service token is not configured."), 503
    if not authorization.startswith("Bearer ") or not hmac.compare_digest(supplied_token, service_token):
        return jsonify(status="error", message="Not authorized."), 401
    return None


@app.route("/internal/students", methods=["GET"])
def internal_students():
    error = require_spark_service_token()
    if error:
        return error
    students = []
    for path in sorted(glob.glob(os.path.join(FACE_DIR, "*.jpg"))):
        ic, name = parse_identity(path)
        if re.fullmatch(r"\d{12}", ic):
            students.append({"ic": ic, "name": name})
    return jsonify(students=students)


@app.route("/internal/enroll", methods=["POST"])
def internal_enroll():
    error = require_spark_service_token()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    ic = re.sub(r"[\s\-]", "", str(data.get("ic", "")))
    name = clean_name(str(data.get("name", "")))
    if not re.fullmatch(r"\d{12}", ic):
        return jsonify(status="error", message="Student IC number must contain exactly 12 digits."), 400
    if not name:
        return jsonify(status="error", message="Student name is required."), 400
    img = decode_image(data.get("image"))
    if img is None:
        return jsonify(status="error", message="Could not read the camera image."), 400
    try:
        from deepface import DeepFace
        with face_lock:
            faces = DeepFace.extract_faces(img_path=img, enforce_detection=True)
            if len(faces) != 1:
                return jsonify(status="error", message="Capture exactly one student's face."), 422
            for old in glob.glob(os.path.join(FACE_DIR, f"{ic}_*.jpg")):
                os.remove(old)
            filename = f"{ic}_{name}.jpg"
            if not cv2.imwrite(os.path.join(FACE_DIR, filename), img, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                return jsonify(status="error", message="Could not save the face photo."), 500
            clear_index_cache()
    except ValueError:
        return jsonify(status="error", message="No clear face found. Face the camera in good light."), 422
    except Exception:
        app.logger.exception("Face enrollment failed")
        return jsonify(status="error", message="Face enrollment failed."), 503
    return jsonify(status="ok", ic=ic, name=name.replace("_", " "))


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

        identity = find_face_identity(frame)
        if identity is None:
            return jsonify(status="unknown")
        ic, name = identity

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


@app.route("/internal/recognize", methods=["POST"])
def internal_recognize():
    """Private recognition-only endpoint for the authenticated SPARK backend."""
    error = require_spark_service_token()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    frame = decode_image(data.get("image"))
    if frame is None:
        return jsonify(status="error", message="Could not read the camera image."), 400
    try:
        identity = find_face_identity(frame)
    except ValueError as exc:
        app.logger.info("No recognizable face in frame: %s", exc)
        return jsonify(status="unknown")
    except Exception:
        app.logger.exception("Face recognition request failed")
        return jsonify(status="error", message="Face recognition failed."), 503
    if identity is None:
        return jsonify(status="unknown")
    ic, name = identity
    return jsonify(status="found", ic=ic, name=name)


# --------------------------------------------------------------------------
# Fallback: manual / bulk attendance (camera or face recognition unavailable)
# --------------------------------------------------------------------------
def get_roster():
    """Roster = students.csv (if imported) merged with every enrolled face photo."""
    roster = {}
    if os.path.exists(ROSTER_FILE):
        with open(ROSTER_FILE, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                ic = (r.get("IC") or "").strip()
                if re.fullmatch(r"\d{12}", ic):
                    roster[ic] = {"ic": ic, "name": (r.get("Name") or "").strip(),
                                  "cls": (r.get("Class") or "").strip(), "enrolled": False}
    for p in glob.glob(os.path.join(FACE_DIR, "*.jpg")):
        ic, name = parse_identity(p)
        if ic in roster:
            roster[ic]["enrolled"] = True
        else:
            roster[ic] = {"ic": ic, "name": name, "cls": "", "enrolled": True}
    return sorted(roster.values(), key=lambda s: (s["cls"], s["name"].lower()))


def logged_today(category, club, day):
    """ICs already logged today for this exact category + club."""
    seen = set()
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, newline="", encoding="utf-8") as f:
            for r in csv.reader(f):
                if len(r) == 6 and r[0].startswith(day) and r[4] == category and r[5] == csv_safe(club):
                    seen.add(r[1])
    return seen


@app.route("/manual")
@login_required()
def manual():
    if not session.get("category") or not session.get("club"):
        return redirect(url_for("setup"))
    return render_template("manual.html", user=session["user"], category=session["category"],
                           club=session["club"], today=datetime.now().strftime("%A, %d %B %Y"))


@app.route("/api/roster")
@login_required()
def api_roster():
    if not session.get("category") or not session.get("club"):
        return jsonify(status="error", message="Session not set up"), 400
    done = logged_today(session["category"], session["club"], datetime.now().strftime("%Y-%m-%d"))
    students = [dict(s, done=s["ic"] in done) for s in get_roster()]
    return jsonify(students=students)


@app.route("/api/manual-attendance", methods=["POST"])
@login_required()
def api_manual_attendance():
    if not session.get("category") or not session.get("club"):
        return jsonify(status="error", message="Session not set up"), 400
    data = request.get_json(silent=True) or {}
    ics = data.get("ics")
    reason = str(data.get("reason", "")).strip()[:120] or "Not given"
    if not isinstance(ics, list) or not ics or len(ics) > 2000:
        return jsonify(status="error", message="Tick at least one student."), 400

    lookup = {s["ic"]: s for s in get_roster()}
    category, club, teacher = session["category"], session["club"], session["user"]
    now = datetime.now().replace(microsecond=0)
    saved, skipped, unknown = [], [], []
    with log_lock:  # one atomic batch: duplicates checked and rows written together
        done = logged_today(category, club, now.strftime("%Y-%m-%d"))
        for ic in dict.fromkeys(str(i) for i in ics):  # de-dupe, keep order
            if ic not in lookup:
                unknown.append(ic)
            elif ic in done:
                skipped.append(ic)
            else:
                write_log(ic, lookup[ic]["name"], teacher, category, club, now)
                saved.append(ic)
        new_audit = not os.path.exists(MANUAL_AUDIT_FILE)
        with open(MANUAL_AUDIT_FILE, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_audit:
                w.writerow(["Timestamp", "Teacher", "PAJSK_Category", "Club_Name",
                            "Reason", "Saved_Count", "Saved_ICs"])
            w.writerow([now.strftime("%Y-%m-%d %H:%M:%S"), teacher, category, csv_safe(club),
                        csv_safe(reason), len(saved), " ".join(saved)])
    return jsonify(status="ok", saved=len(saved), skipped=len(skipped), unknown=len(unknown))


@app.route("/api/roster/import", methods=["POST"])
@login_required("admin")
def api_roster_import():
    """Admin uploads a CSV with columns IC, Name[, Class]; merges into students.csv."""
    f = request.files.get("file")
    if not f:
        return jsonify(status="error", message="Choose a CSV file."), 400
    try:
        text = f.read().decode("utf-8-sig")
        reader = csv.DictReader(text.splitlines())
        cols = {(c or "").strip().lower(): c for c in (reader.fieldnames or [])}
        if "ic" not in cols or "name" not in cols:
            return jsonify(status="error", message="CSV needs the columns IC and Name (Class is optional)."), 400
        existing = {}
        if os.path.exists(ROSTER_FILE):
            with open(ROSTER_FILE, newline="", encoding="utf-8-sig") as g:
                for r in csv.DictReader(g):
                    existing[r["IC"]] = r
        added = bad = 0
        for r in reader:
            ic = re.sub(r"[\s\-]", "", (r.get(cols["ic"]) or ""))
            name = " ".join((r.get(cols["name"]) or "").split())
            cls = " ".join((r.get(cols.get("class", ""), "") or "").split())
            if not re.fullmatch(r"\d{12}", ic) or not name:
                bad += 1
                continue
            existing[ic] = {"IC": ic, "Name": name, "Class": cls}
            added += 1
        with open(ROSTER_FILE, "w", newline="", encoding="utf-8") as g:
            w = csv.DictWriter(g, fieldnames=["IC", "Name", "Class"])
            w.writeheader()
            w.writerows(existing.values())
        return jsonify(status="ok", added=added, bad=bad, total=len(existing))
    except Exception:
        return jsonify(status="error", message="Could not read that file. Save it as UTF-8 CSV."), 400


if __name__ == "__main__":
    load_users()
    # getUserMedia works on localhost; use HTTPS for any other host/device.
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
