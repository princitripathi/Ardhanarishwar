import os
import tempfile
import sqlite3
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ---- Model validation tests ----
from app.interview.models import InterviewCreateRequest
from pydantic import ValidationError


# ---- Service tests with isolated DB ----

@pytest.fixture
def temp_db(tmp_path):
    """Create isolated temp DB and patch service DB_PATH"""
    db_file = tmp_path / "test_interviews.db"
    # Patch DB_PATH in service module before any service calls
    # Need to ensure init_db creates tables in temp file
    import app.interview.service as svc
    original_db_path = svc.DB_PATH
    svc.DB_PATH = str(db_file)
    svc.init_db()
    yield str(db_file)
    # restore
    svc.DB_PATH = original_db_path
    # cleanup done by tmp_path


def make_payload(overrides=None):
    base = {
        "candidate_name": "John Doe",
        "candidate_email": "john@example.com",
        "job_title": "AI Engineer",
        "job_description": "Build AI systems with Python and LLM expertise required.",
        "resume_text": "John has 5 years experience in Python, ML, and LLMs...",
        "scheduled_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
        "scheduled_time": "10:00",
        "duration_minutes": 30,
    }
    if overrides:
        base.update(overrides)
    return base


class TestInterviewModels:
    def test_valid_payload(self):
        data = make_payload()
        req = InterviewCreateRequest(**data)
        assert req.candidate_name == "John Doe"
        assert req.duration_minutes == 30

    def test_candidate_name_required(self):
        data = make_payload({"candidate_name": ""})
        with pytest.raises(ValidationError):
            InterviewCreateRequest(**data)

    def test_candidate_name_too_short(self):
        data = make_payload({"candidate_name": "A"})
        with pytest.raises(ValidationError):
            InterviewCreateRequest(**data)

    def test_invalid_email(self):
        data = make_payload({"candidate_email": "not-an-email"})
        with pytest.raises(ValidationError):
            InterviewCreateRequest(**data)

    def test_empty_email_allowed(self):
        data = make_payload({"candidate_email": ""})
        req = InterviewCreateRequest(**data)
        assert req.candidate_email is None

    def test_none_email_allowed(self):
        data = make_payload({"candidate_email": None})
        req = InterviewCreateRequest(**data)
        assert req.candidate_email is None

    def test_job_description_too_short(self):
        data = make_payload({"job_description": "short"})
        with pytest.raises(ValidationError):
            InterviewCreateRequest(**data)

    def test_resume_too_short(self):
        data = make_payload({"resume_text": "short"})
        with pytest.raises(ValidationError):
            InterviewCreateRequest(**data)

    def test_invalid_date_format(self):
        data = make_payload({"scheduled_date": "2026/01/01"})
        with pytest.raises(ValidationError):
            InterviewCreateRequest(**data)

    def test_invalid_time_format(self):
        data = make_payload({"scheduled_time": "25:00"})
        with pytest.raises(ValidationError):
            InterviewCreateRequest(**data)

    def test_time_normalization(self):
        data = make_payload({"scheduled_time": "09:05:00"})
        req = InterviewCreateRequest(**data)
        assert req.scheduled_time == "09:05"

    def test_duration_out_of_range_low(self):
        data = make_payload({"duration_minutes": 2})
        with pytest.raises(ValidationError):
            InterviewCreateRequest(**data)

    def test_duration_out_of_range_high(self):
        data = make_payload({"duration_minutes": 200})
        with pytest.raises(ValidationError):
            InterviewCreateRequest(**data)

    def test_duration_not_int(self):
        data = make_payload({"duration_minutes": "30"})  # type: ignore
        # Pydantic will coerce string "30" to int, so test with float
        data2 = make_payload({"duration_minutes": 30.5})  # type: ignore
        with pytest.raises(ValidationError):
            InterviewCreateRequest(**data2)


class TestInterviewService:
    def test_create_and_get(self, temp_db):
        import app.interview.service as svc
        payload = make_payload()
        created = svc.create_interview(payload)
        assert created["candidate_name"] == "John Doe"
        assert created["status"] == "scheduled"
        assert len(created["interview_id"]) == 12
        fetched = svc.get_interview(created["interview_id"])
        assert fetched["interview_id"] == created["interview_id"]

    def test_get_nonexistent(self, temp_db):
        import app.interview.service as svc
        assert svc.get_interview("nonexistent") is None

    def test_list_ordering(self, temp_db):
        import app.interview.service as svc
        p1 = svc.create_interview(make_payload({"candidate_name": "Alice"}))
        p2 = svc.create_interview(make_payload({"candidate_name": "Bob"}))
        lst = svc.list_interviews()
        assert len(lst) >= 2
        # Most recent first
        assert lst[0]["candidate_name"] == "Bob"

    def test_update_status(self, temp_db):
        import app.interview.service as svc
        created = svc.create_interview(make_payload())
        updated = svc.update_status(created["interview_id"], "active")
        assert updated["status"] == "active"

    def test_get_scheduled_datetime_valid(self, temp_db):
        import app.interview.service as svc
        interview = {"scheduled_date": "2026-09-02", "scheduled_time": "14:30", "duration_minutes": 30}
        dt = svc.get_scheduled_datetime(interview)
        assert dt == datetime(2026, 9, 2, 14, 30)

    def test_get_scheduled_datetime_with_seconds(self, temp_db):
        import app.interview.service as svc
        # Service handles HH:MM via models normalization, but direct calls test HH:MM:SS
        # Need to bypass model; test with raw string containing seconds
        # get_scheduled_datetime supports both formats, so test HH:MM:SS directly via row-like dict
        interview = {"scheduled_date": "2026-09-02", "scheduled_time": "14:30:00", "duration_minutes": 30}
        dt = svc.get_scheduled_datetime(interview)
        assert dt == datetime(2026, 9, 2, 14, 30, 0)

    def test_get_scheduled_datetime_invalid(self):
        import app.interview.service as svc
        interview = {"scheduled_date": "invalid", "scheduled_time": "14:30", "duration_minutes": 30}
        with pytest.raises(ValueError):
            svc.get_scheduled_datetime(interview)

    def test_window_not_started(self, temp_db):
        import app.interview.service as svc
        future = datetime.now() + timedelta(hours=2)
        payload = make_payload({
            "scheduled_date": future.strftime("%Y-%m-%d"),
            "scheduled_time": future.strftime("%H:%M"),
            "duration_minutes": 30,
        })
        iv = svc.create_interview(payload)
        info = svc.get_window_info(iv)
        assert info["can_join"] is False
        assert info["status"] == "not_started"
        assert "not started" in info["message"].lower()

    def test_window_joinable(self, temp_db):
        import app.interview.service as svc
        # Schedule 2 minutes ago => within 5 min early window
        now = datetime.now() - timedelta(minutes=2)
        payload = make_payload({
            "scheduled_date": now.strftime("%Y-%m-%d"),
            "scheduled_time": now.strftime("%H:%M"),
            "duration_minutes": 30,
        })
        iv = svc.create_interview(payload)
        info = svc.get_window_info(iv)
        assert info["can_join"] is True
        assert info["status"] == "joinable"

    def test_window_ended(self, temp_db):
        import app.interview.service as svc
        past = datetime.now() - timedelta(hours=2)
        payload = make_payload({
            "scheduled_date": past.strftime("%Y-%m-%d"),
            "scheduled_time": past.strftime("%H:%M"),
            "duration_minutes": 30,
        })
        iv = svc.create_interview(payload)
        info = svc.get_window_info(iv)
        assert info["can_join"] is False
        assert info["status"] == "ended"

    def test_window_cancelled(self, temp_db):
        import app.interview.service as svc
        iv = svc.create_interview(make_payload())
        svc.update_status(iv["interview_id"], "cancelled")
        iv2 = svc.get_interview(iv["interview_id"])
        info = svc.get_window_info(iv2)
        assert info["can_join"] is False
        assert info["status"] == "cancelled"

    def test_window_completed(self, temp_db):
        import app.interview.service as svc
        iv = svc.create_interview(make_payload())
        svc.update_status(iv["interview_id"], "completed")
        iv2 = svc.get_interview(iv["interview_id"])
        info = svc.get_window_info(iv2)
        assert info["can_join"] is False
        assert info["status"] == "completed"

    def test_window_invalid_datetime(self, temp_db):
        import app.interview.service as svc
        # Insert invalid manually
        conn = svc.get_connection()
        cur = conn.cursor()
        iid = uuid.uuid4().hex[:12]
        cur.execute("INSERT INTO interview_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (iid, "Test", None, "Job", "Desc 12345", "Resume 12345", "bad-date", "bad-time", 30, "scheduled", datetime.utcnow().isoformat()+"Z"))
        conn.commit()
        conn.close()
        iv = svc.get_interview(iid)
        info = svc.get_window_info(iv)
        assert info["status"] == "invalid"
        assert info["can_join"] is False

    def test_can_start_success(self, temp_db):
        import app.interview.service as svc
        now = datetime.now() - timedelta(minutes=1)
        payload = make_payload({
            "scheduled_date": now.strftime("%Y-%m-%d"),
            "scheduled_time": now.strftime("%H:%M"),
        })
        iv = svc.create_interview(payload)
        can, msg = svc.can_start(iv)
        assert can is True

    def test_can_start_not_scheduled_active(self, temp_db):
        import app.interview.service as svc
        now = datetime.now() - timedelta(minutes=1)
        payload = make_payload({
            "scheduled_date": now.strftime("%Y-%m-%d"),
            "scheduled_time": now.strftime("%H:%M"),
        })
        iv = svc.create_interview(payload)
        svc.update_status(iv["interview_id"], "active")
        iv2 = svc.get_interview(iv["interview_id"])
        can, msg = svc.can_start(iv2)
        assert can is False
        assert "already active" in msg.lower()

    def test_can_start_cancelled(self, temp_db):
        import app.interview.service as svc
        iv = svc.create_interview(make_payload())
        svc.update_status(iv["interview_id"], "cancelled")
        iv2 = svc.get_interview(iv["interview_id"])
        can, msg = svc.can_start(iv2)
        assert can is False
        assert "cancelled" in msg.lower()

    def test_can_start_not_yet(self, temp_db):
        import app.interview.service as svc
        future = datetime.now() + timedelta(hours=2)
        payload = make_payload({
            "scheduled_date": future.strftime("%Y-%m-%d"),
            "scheduled_time": future.strftime("%H:%M"),
        })
        iv = svc.create_interview(payload)
        can, msg = svc.can_start(iv)
        assert can is False


# ---- API Route Tests with TestClient and isolated DB ----

@pytest.fixture
def client(temp_db):
    # temp_db already patches DB_PATH, now create client
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_api_create_interview(client):
    payload = make_payload()
    resp = client.post("/api/interviews", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "interview_id" in data
    assert data["status"] == "scheduled"
    assert data["candidate_name"] == "John Doe"


def test_api_create_invalid_returns_422(client):
    payload = make_payload({"candidate_name": ""})
    resp = client.post("/api/interviews", json=payload)
    assert resp.status_code == 422  # FastAPI validation


def test_api_create_missing_fields_422(client):
    resp = client.post("/api/interviews", json={"candidate_name": "A"})
    assert resp.status_code == 422


def test_api_list_interviews(client):
    # create two
    client.post("/api/interviews", json=make_payload({"candidate_name": "ListTest1"}))
    client.post("/api/interviews", json=make_payload({"candidate_name": "ListTest2"}))
    resp = client.get("/api/interviews")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2


def test_api_get_interview_with_window(client):
    payload = make_payload()
    created = client.post("/api/interviews", json=payload).json()
    iid = created["interview_id"]
    resp = client.get(f"/api/interviews/{iid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["interview_id"] == iid
    assert "window" in data
    assert "can_join" in data["window"]


def test_api_get_not_found(client):
    resp = client.get("/api/interviews/nonexistent123")
    assert resp.status_code == 404


def test_api_start_interview_success(client):
    now = datetime.now() - timedelta(minutes=1)
    payload = make_payload({
        "scheduled_date": now.strftime("%Y-%m-%d"),
        "scheduled_time": now.strftime("%H:%M"),
        "candidate_name": "Startable",
    })
    created = client.post("/api/interviews", json=payload).json()
    iid = created["interview_id"]
    resp = client.post(f"/api/interviews/{iid}/start")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"


def test_api_start_interview_not_yet(client):
    future = datetime.now() + timedelta(hours=5)
    payload = make_payload({
        "scheduled_date": future.strftime("%Y-%m-%d"),
        "scheduled_time": future.strftime("%H:%M"),
        "candidate_name": "FutureGuy",
    })
    created = client.post("/api/interviews", json=payload).json()
    iid = created["interview_id"]
    resp = client.post(f"/api/interviews/{iid}/start")
    assert resp.status_code == 400
    assert "not started" in resp.json()["detail"].lower()


def test_api_start_already_active(client):
    now = datetime.now() - timedelta(minutes=1)
    payload = make_payload({
        "scheduled_date": now.strftime("%Y-%m-%d"),
        "scheduled_time": now.strftime("%H:%M"),
        "candidate_name": "DoubleStart",
    })
    iid = client.post("/api/interviews", json=payload).json()["interview_id"]
    client.post(f"/api/interviews/{iid}/start")
    resp2 = client.post(f"/api/interviews/{iid}/start")
    assert resp2.status_code == 400
    assert "already active" in resp2.json()["detail"].lower()


def test_api_start_cancelled_fails(client):
    iid = client.post("/api/interviews", json=make_payload({"candidate_name": "ToCancelStart"})).json()["interview_id"]
    client.post(f"/api/interviews/{iid}/cancel")
    resp = client.post(f"/api/interviews/{iid}/start")
    assert resp.status_code == 400


def test_api_cancel_success(client):
    iid = client.post("/api/interviews", json=make_payload({"candidate_name": "CancelMe"})).json()["interview_id"]
    resp = client.post(f"/api/interviews/{iid}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_api_cancel_already_cancelled(client):
    iid = client.post("/api/interviews", json=make_payload({"candidate_name": "CancelTwice"})).json()["interview_id"]
    client.post(f"/api/interviews/{iid}/cancel")
    resp = client.post(f"/api/interviews/{iid}/cancel")
    assert resp.status_code == 400


def test_api_cancel_completed_fails(client):
    # Manually set to completed via service
    import app.interview.service as svc
    now = datetime.now() - timedelta(minutes=1)
    payload = make_payload({
        "scheduled_date": now.strftime("%Y-%m-%d"),
        "scheduled_time": now.strftime("%H:%M"),
        "candidate_name": "CompleteThenCancel",
    })
    iid = client.post("/api/interviews", json=payload).json()["interview_id"]
    # start -> active then manually mark completed
    client.post(f"/api/interviews/{iid}/start")
    # directly update to completed
    svc.update_status(iid, "completed")
    resp = client.post(f"/api/interviews/{iid}/cancel")
    assert resp.status_code == 400
    assert "completed" in resp.json()["detail"].lower()


def test_api_cancel_not_found(client):
    resp = client.post("/api/interviews/doesnotexist/cancel")
    assert resp.status_code == 404


def test_api_get_after_cancel_shows_cancelled_window(client):
    iid = client.post("/api/interviews", json=make_payload({"candidate_name": "CheckWindow"})).json()["interview_id"]
    client.post(f"/api/interviews/{iid}/cancel")
    data = client.get(f"/api/interviews/{iid}").json()
    assert data["status"] == "cancelled"
    assert data["window"]["status"] == "cancelled"
    assert data["window"]["can_join"] is False


def test_api_duration_boundary_accepted(client):
    for dur in [5, 120]:
        payload = make_payload({"duration_minutes": dur, "candidate_name": f"Dur{dur}"})
        resp = client.post("/api/interviews", json=payload)
        assert resp.status_code == 201, f"duration {dur} should be accepted"


def test_api_duration_boundary_rejected(client):
    for dur in [4, 121]:
        payload = make_payload({"duration_minutes": dur, "candidate_name": f"Bad{dur}"})
        resp = client.post("/api/interviews", json=payload)
        assert resp.status_code == 422, f"duration {dur} should be rejected"
