import sqlite3
import os
import uuid
import json
from datetime import datetime
from typing import Optional, Dict, List

from app.interview.service import get_interview, get_window_info, update_status
import app.interview.service as interview_service

# Determine DB_PATH same as interview service
DB_PATH = interview_service.DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_session_db():
    # ensure base interview table exists first
    interview_service.init_db()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS interview_ai_sessions (
            session_id TEXT PRIMARY KEY,
            interview_id TEXT NOT NULL,
            status TEXT NOT NULL,
            total_questions INTEGER NOT NULL,
            question_number INTEGER NOT NULL,
            current_topic TEXT,
            interview_plan TEXT NOT NULL,
            questions_asked TEXT NOT NULL,
            answers TEXT NOT NULL,
            evaluations TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            final_report TEXT,
            FOREIGN KEY (interview_id) REFERENCES interview_sessions(interview_id)
        )
    """)
    # index for lookup by interview
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_session_interview ON interview_ai_sessions(interview_id)")
    conn.commit()
    conn.close()


# Initialize on import
init_session_db()


def _row_to_dict(row) -> Optional[Dict]:
    if row is None:
        return None
    d = dict(row)
    # parse JSON fields
    for k in ("interview_plan", "questions_asked", "answers", "evaluations", "final_report"):
        if k in d and d[k] is not None:
            try:
                d[k] = json.loads(d[k]) if isinstance(d[k], str) else d[k]
            except Exception:
                d[k] = None
        # keep consistent defaults
    if d.get("questions_asked") is None:
        d["questions_asked"] = []
    if d.get("answers") is None:
        d["answers"] = []
    if d.get("evaluations") is None:
        d["evaluations"] = []
    return d


def _serialize(d: Dict) -> Dict:
    out = dict(d)
    for k in ("interview_plan", "questions_asked", "answers", "evaluations", "final_report"):
        if k in out and out[k] is not None and not isinstance(out[k], str):
            out[k] = json.dumps(out[k])
    return out


def get_session(session_id: str) -> Optional[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM interview_ai_sessions WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_dict(row)


def get_session_by_interview(interview_id: str) -> Optional[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    # get most recent session for interview
    cur.execute("SELECT * FROM interview_ai_sessions WHERE interview_id = ? ORDER BY started_at DESC LIMIT 1", (interview_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_dict(row)


def list_sessions_for_interview(interview_id: str) -> List[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM interview_ai_sessions WHERE interview_id = ? ORDER BY started_at DESC", (interview_id,))
    rows = cur.fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def create_session(interview_id: str, interview_plan: Dict, first_question: Dict, total_questions: int) -> Dict:
    session_id = uuid.uuid4().hex[:16]
    started_at = datetime.utcnow().isoformat() + "Z"
    current_topic = first_question.get("topic", interview_plan["topics"][0]["name"] if interview_plan.get("topics") else None)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO interview_ai_sessions
        (session_id, interview_id, status, total_questions, question_number, current_topic, interview_plan, questions_asked, answers, evaluations, started_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        interview_id,
        "active",
        total_questions,
        1,
        current_topic,
        json.dumps(interview_plan),
        json.dumps([first_question]),
        json.dumps([]),
        json.dumps([]),
        started_at,
    ))
    conn.commit()
    conn.close()
    return get_session(session_id)


def update_session(session_id: str, updates: Dict) -> Optional[Dict]:
    # allowed keys: status, question_number, current_topic, questions_asked, answers, evaluations, completed_at, final_report, total_questions
    allowed = {"status", "question_number", "current_topic", "questions_asked", "answers", "evaluations", "completed_at", "final_report", "total_questions"}
    fields = []
    values = []
    for k, v in updates.items():
        if k not in allowed:
            continue
        if k in ("questions_asked", "answers", "evaluations", "interview_plan", "final_report"):
            if not isinstance(v, str):
                v = json.dumps(v)
        fields.append(f"{k} = ?")
        values.append(v)
    if not fields:
        return get_session(session_id)
    values.append(session_id)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"UPDATE interview_ai_sessions SET {', '.join(fields)} WHERE session_id = ?", tuple(values))
    conn.commit()
    conn.close()
    return get_session(session_id)


def append_answer_and_evaluation(session_id: str, answer: str, evaluation: Dict, next_question: Optional[Dict] = None) -> Optional[Dict]:
    sess = get_session(session_id)
    if not sess:
        return None
    answers = sess.get("answers") or []
    evaluations = sess.get("evaluations") or []
    questions = sess.get("questions_asked") or []
    answers.append({"question_number": sess["question_number"], "answer": answer, "timestamp": datetime.utcnow().isoformat()+"Z"})
    evaluations.append(evaluation)
    updates = {
        "answers": answers,
        "evaluations": evaluations,
    }
    if next_question:
        questions.append(next_question)
        updates["questions_asked"] = questions
        updates["question_number"] = next_question["question_number"]
        updates["current_topic"] = next_question.get("topic")
    # status may already be completed handled elsewhere
    return update_session(session_id, updates)


def complete_session(session_id: str, final_report: Dict) -> Optional[Dict]:
    completed_at = datetime.utcnow().isoformat() + "Z"
    updates = {
        "status": "completed",
        "completed_at": completed_at,
        "final_report": final_report,
    }
    sess = update_session(session_id, updates)
    # also update interview status to completed
    if sess:
        try:
            interview = get_interview(sess["interview_id"])
            if interview and interview["status"] != "completed":
                update_status(sess["interview_id"], "completed")
        except Exception:
            pass
    return get_session(session_id)


def delete_sessions_for_interview(interview_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM interview_ai_sessions WHERE interview_id = ?", (interview_id,))
    conn.commit()
    conn.close()
