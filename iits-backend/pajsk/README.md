# PAJSK Attendance & Face Registration

    pip install -r requirements.txt
    python app.py          # http://127.0.0.1:5000

First run creates `coaches.json` with default logins: `admin / admin123`, `coach1 / coach123`.
Change them (generate hashes with `werkzeug.security.generate_password_hash`).

- Face photos: `face_db/{IC}_{FULL_NAME}.jpg`
- Log: `attendance_log.csv` (Timestamp, Student_IC, Student_Name, Teacher_Logged_In, PAJSK_Category, Club_Name)
- Camera access needs `localhost` or HTTPS. Set `PAJSK_SECRET` for a stable session key.
- First scan after startup/enrolment is slow while FaceNet512 loads and the index rebuilds.
