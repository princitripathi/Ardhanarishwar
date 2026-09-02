import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient


def make_payload(overrides=None):
    base = {
        "candidate_name": "CountTester",
        "candidate_email": "count@test.com",
        "job_title": "AI Engineer",
        "job_description": "Build AI systems with Python and LLM expertise required. Must know vector databases and RAG.",
        "resume_text": "5 years experience in Python, ML, FAISS project for semantic retrieval, PyTorch.",
        "scheduled_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
        "scheduled_time": "10:00",
        "duration_minutes": 30,
    }
    if overrides:
        base.update(overrides)
    return base

def mock_plan():
    return {
        "topics": [
            {"name": "Introduction", "focus": "Intro"},
            {"name": "Resume & Projects", "focus": "Projects"},
            {"name": "Python", "focus": "Python"},
            {"name": "Machine Learning", "focus": "ML"},
            {"name": "Generative AI / LLM", "focus": "LLM"},
            {"name": "Problem Solving", "focus": "Problem"},
            {"name": "Behavioral & Communication", "focus": "Behavioral"},
        ]
    }

def mock_question(qnum, topic="Python", difficulty="medium", is_follow=False):
    return {
        "question": f"Mock question {qnum} about {topic}?",
        "topic": topic,
        "difficulty": difficulty,
        "question_number": qnum,
        "expected_focus": "Mock expected",
        "is_follow_up": is_follow,
    }

def mock_eval(score=7):
    return {
        "score": score,
        "correctness": score,
        "relevance": score,
        "depth": score,
        "clarity": score,
        "feedback": "Good answer",
        "strengths": ["Good detail"],
        "weaknesses": ["Could be deeper"],
        "follow_up_needed": False,
        "inconsistency_flag": False,
        "inconsistency_note": None,
        "difficulty_adjustment": "maintain",
    }

def mock_report():
    return {
        "overall_score": 7,
        "technical_score": 7,
        "communication_score": 7,
        "problem_solving_score": 6,
        "strengths": ["Good ML knowledge"],
        "weaknesses": ["Needs more depth"],
        "topics_covered": ["Python", "Machine Learning"],
        "recommendation": "Moderate",
        "summary": "Moderate performance",
        "detailed_feedback": "Detailed feedback",
    }

def _topic_for(kwargs):
    plan = kwargs.get("interview_plan", {})
    topics = [t["name"] for t in plan.get("topics", [])] if plan else ["Python"]
    qnum = kwargs.get("question_number", 1)
    idx = min(qnum-1, len(topics)-1) if topics else 0
    return topics[idx] if topics else "Python"


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_count.db"
    import app.interview.service as svc
    import app.interview.session_service as sess
    orig = svc.DB_PATH
    orig_sess = sess.DB_PATH
    svc.DB_PATH = str(db_file)
    sess.DB_PATH = str(db_file)
    svc.init_db()
    sess.init_session_db()
    yield str(db_file)
    svc.DB_PATH = orig
    sess.DB_PATH = orig_sess


@pytest.fixture
def client(temp_db):
    from app.main import app
    with TestClient(app) as c:
        yield c


def _create_interview(client, name="CountTest"):
    now = datetime.now() - timedelta(minutes=1)
    payload = make_payload({
        "scheduled_date": now.strftime("%Y-%m-%d"),
        "scheduled_time": now.strftime("%H:%M"),
        "candidate_name": name,
    })
    resp = client.post("/api/interviews", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["interview_id"]


class TestQuestionCountValidation:
    def test_3_allowed_in_development(self, client, temp_db, monkeypatch):
        monkeypatch.setenv("APP_ENV", "development")
        iid = _create_interview(client, "Dev3Allowed")
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(return_value=mock_question(1, "Introduction"))):
            resp = client.post(f"/api/interviews/{iid}/session/start", json={"total_questions": 3})
            assert resp.status_code == 200, resp.text
            assert resp.json()["total_questions"] == 3

    def test_3_rejected_in_production(self, client, temp_db, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        iid = _create_interview(client, "Prod3Rejected")
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(return_value=mock_question(1))):
            resp = client.post(f"/api/interviews/{iid}/session/start", json={"total_questions": 3})
            assert resp.status_code == 422, resp.text
            assert "5 and 30" in resp.json()["detail"]

    def test_5_10_15_20_allowed_in_production(self, client, temp_db, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        for total in [5, 10, 15, 20]:
            iid = _create_interview(client, f"Prod{total}")
            with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
                 patch("app.interview.session_routes.generate_next_question", new=AsyncMock(return_value=mock_question(1))):
                resp = client.post(f"/api/interviews/{iid}/session/start", json={"total_questions": total})
                assert resp.status_code == 200, f"total {total} should be allowed in production: {resp.text}"
                assert resp.json()["total_questions"] == total

    def test_5_30_range_preserved(self, client, temp_db, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        iid = _create_interview(client, "RangeCheck")
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(return_value=mock_question(1))):
            for bad in [4, 31, 0, 100]:
                resp = client.post(f"/api/interviews/{iid}/session/start", json={"total_questions": bad})
                assert resp.status_code in (422, 400), f"{bad} should be rejected"
        # valid edges 5 and 30
        iid2 = _create_interview(client, "Edge5")
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(return_value=mock_question(1))):
            resp = client.post(f"/api/interviews/{iid2}/session/start", json={"total_questions": 5})
            assert resp.status_code == 200
        iid3 = _create_interview(client, "Edge30")
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(return_value=mock_question(1))):
            resp = client.post(f"/api/interviews/{iid3}/session/start", json={"total_questions": 30})
            assert resp.status_code == 200

    def test_default_is_10(self, client, temp_db, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        iid = _create_interview(client, "Default10")
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(return_value=mock_question(1))):
            resp = client.post(f"/api/interviews/{iid}/session/start", json={})
            assert resp.status_code == 200
            assert resp.json()["total_questions"] == 10


class TestCompletionByQuestionCount:
    def _start_session(self, client, total, monkeypatch):
        monkeypatch.setenv("APP_ENV", "development")
        iid = _create_interview(client, f"Comp{total}")
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda **kw: mock_question(kw.get("question_number",1), _topic_for(kw)))), \
             patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/start", json={"total_questions": total})
            assert resp.status_code == 200, resp.text
            return iid, resp.json()["session_id"]

    def test_completion_3_questions_dev(self, client, temp_db, monkeypatch):
        iid, sid = self._start_session(client, 3, monkeypatch)
        # Need 3 answers to complete
        for i in range(2):
            with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
                 patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda **kw: mock_question(kw.get("question_number"), _topic_for(kw)))), \
                 patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
                resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": f"answer {i+1}"})
                assert resp.status_code == 200
                assert resp.json()["status"] == "active"
        # final answer -> completed
        with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": "final answer"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "completed"
            assert "final_report" in resp.json()

    def test_completion_5_questions(self, client, temp_db, monkeypatch):
        iid, sid = self._start_session(client, 5, monkeypatch)
        for i in range(4):
            with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
                 patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda **kw: mock_question(kw.get("question_number"), _topic_for(kw)))), \
                 patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
                resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": f"ans {i}"})
                assert resp.status_code == 200
                assert resp.json()["status"] == "active"
        with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": "final"})
            assert resp.json()["status"] == "completed"
            assert "final_report" in resp.json()

    def test_completion_10_questions(self, client, temp_db, monkeypatch):
        iid, sid = self._start_session(client, 10, monkeypatch)
        for i in range(9):
            with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
                 patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda **kw: mock_question(kw.get("question_number"), _topic_for(kw)))), \
                 patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
                resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": f"ans {i}"})
                assert resp.status_code == 200
                assert resp.json()["status"] == "active"
        with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": "final"})
            assert resp.json()["status"] == "completed"
            assert "final_report" in resp.json()
            # verify adaptive flow preserved: evaluations were called, report generated
            assert resp.json()["final_report"]["recommendation"] in ["Strong", "Moderate", "Needs Improvement"]
