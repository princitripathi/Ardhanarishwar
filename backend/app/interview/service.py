import sqlite3
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "interviews.db")
# Fallback to backend/data if data folder is at project root
_alt = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "interviews.db")
# Actually project structure: backend/app/interview/service.py -> ../../.. = Ardhanarishwar root, then data/interviews.db
# Use that if exists, else use backend/data
if not os.path.exists(os.path.dirname(_alt)):
    # try backend/data
    _backend_data = os.path.join(os.path.dirname(__file__), "..", "data", "interviews.db")
    DB_PATH = _backend_data

# Ensure directory exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Also ensure alternative path directory
_alt_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
if os.path.exists(os.path.dirname(_alt)):
    # Use project root data if available, prefer it
    DB_PATH = _alt
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS interview_sessions (
            interview_id TEXT PRIMARY KEY,
            candidate_name TEXT NOT NULL,
            candidate_email TEXT,
            job_title TEXT NOT NULL,
            job_description TEXT NOT NULL,
            resume_text TEXT NOT NULL,
            scheduled_date TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# Initialize on import
init_db()

def _row_to_dict(row) -> Dict:
    if row is None:
        return None
    d = dict(row)
    return d

def create_interview(data: dict) -> Dict:
    interview_id = uuid.uuid4().hex[:12]
    created_at = datetime.utcnow().isoformat() + "Z"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO interview_sessions
        (interview_id, candidate_name, candidate_email, job_title, job_description, resume_text, scheduled_date, scheduled_time, duration_minutes, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        interview_id,
        data["candidate_name"],
        data.get("candidate_email"),
        data["job_title"],
        data["job_description"],
        data["resume_text"],
        data["scheduled_date"],
        data["scheduled_time"],
        data["duration_minutes"],
        "scheduled",
        created_at,
    ))
    conn.commit()
    conn.close()
    return get_interview(interview_id)

def get_interview(interview_id: str) -> Optional[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM interview_sessions WHERE interview_id = ?", (interview_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_dict(row)

def list_interviews() -> List[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM interview_sessions ORDER BY created_at DESC, rowid DESC")
    rows = cur.fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]

def update_status(interview_id: str, status: str) -> Optional[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE interview_sessions SET status = ? WHERE interview_id = ?", (status, interview_id))
    conn.commit()
    conn.close()
    return get_interview(interview_id)

def get_scheduled_datetime(interview: Dict) -> datetime:
    # Combine date and time, assume local time (server time)
    dt_str = f"{interview['scheduled_date']} {interview['scheduled_time']}"
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    raise ValueError("Invalid scheduled datetime")

def get_window_info(interview: Dict) -> Dict:
    if interview is None:
        return None
    status = interview["status"]
    if status == "cancelled":
        return {
            "can_join": False,
            "status": "cancelled",
            "message": "Interview has been cancelled.",
            "window_start": None,
            "window_end": None,
        }
    if status == "completed":
        return {
            "can_join": False,
            "status": "completed",
            "message": "Interview has been completed.",
            "window_start": None,
            "window_end": None,
        }
    try:
        scheduled_dt = get_scheduled_datetime(interview)
    except ValueError:
        return {
            "can_join": False,
            "status": "invalid",
            "message": "Invalid scheduled time.",
            "window_start": None,
            "window_end": None,
        }
    duration = interview["duration_minutes"]
    window_start = scheduled_dt - timedelta(minutes=5)
    window_end = scheduled_dt + timedelta(minutes=duration)
    now = datetime.now()

    window_start_str = window_start.isoformat()
    window_end_str = window_end.isoformat()

    if now < window_start:
        return {
            "can_join": False,
            "status": "not_started",
            "message": "Interview has not started yet. Available 5 minutes before scheduled time.",
            "window_start": window_start_str,
            "window_end": window_end_str,
        }
    elif now <= window_end:
        return {
            "can_join": True,
            "status": "joinable",
            "message": "Join Interview",
            "window_start": window_start_str,
            "window_end": window_end_str,
        }
    else:
        return {
            "can_join": False,
            "status": "ended",
            "message": "Interview window has ended.",
            "window_start": window_start_str,
            "window_end": window_end_str,
        }

def can_start(interview: Dict) -> (bool, str):
    info = get_window_info(interview)
    if interview["status"] != "scheduled":
        if interview["status"] == "active":
            return False, "Interview is already active."
        if interview["status"] == "cancelled":
            return False, "Interview has been cancelled."
        if interview["status"] == "completed":
            return False, "Interview has been completed."
        return False, f"Interview status is {interview['status']}."
    if not info["can_join"]:
        return False, info["message"]
    return True, "OK"
