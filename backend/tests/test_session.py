import sqlite3
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.interview.models import InterviewCreateRequest

# Helper to make payload
def make_payload(overrides=None):
    base = {
        "candidate_name": "John Doe",
        "candidate_email": "john@example.com",
        "job_title": "AI Engineer",
        "job_description": "Build AI systems with Python and LLM expertise required. Must know vector databases and RAG.",
        "resume_text": "John has 5 years experience in Python, ML, FAISS project for semantic retrieval, PyTorch, and LLM fine-tuning.",
        "scheduled_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
        "scheduled_time": "10:00",
        "duration_minutes": 30,
    }
    if overrides:
        base.update(overrides)
    return base


@pytest.fixture
def temp_db(tmp_path):
    """Isolated DB for both interview and session tables."""
    db_file = tmp_path / "test_session.db"
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


# Mock LLM helpers to be deterministic
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
        "question": f"Mock question {qnum} about {topic}? (FAISS detail)" if qnum>1 else "Mock intro question about yourself?",
        "topic": topic,
        "difficulty": difficulty,
        "question_number": qnum,
        "expected_focus": "Mock expected",
        "is_follow_up": is_follow,
    }

def mock_eval(score=7, follow=False, diff="maintain"):
    return {
        "score": score,
        "correctness": score,
        "relevance": score,
        "depth": score,
        "clarity": score,
        "feedback": "Good answer",
        "strengths": ["Good detail"],
        "weaknesses": ["Could be deeper"],
        "follow_up_needed": follow,
        "inconsistency_flag": False,
        "inconsistency_note": None,
        "difficulty_adjustment": diff,
    }

def mock_report():
    return {
        "overall_score": 7,
        "technical_score": 7,
        "communication_score": 7,
        "problem_solving_score": 6,
        "strengths": ["Good ML knowledge"],
        "weaknesses": ["Needs more depth on LLMs"],
        "topics_covered": ["Python", "Machine Learning"],
        "recommendation": "Moderate",
        "summary": "Moderate performance",
        "detailed_feedback": "Detailed feedback",
    }

# Setup mocks fixture
@pytest.fixture
def mock_llm():
    with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
         patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda **kwargs: mock_question(kwargs.get("question_number",1), kwargs.get("interview_plan",{}).get("topics",[{}])[0].get("name","Python") if False else _topic_for(kwargs)))) , \
         patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
         patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
        yield

def _topic_for(kwargs):
    plan = kwargs.get("interview_plan", {})
    topics = [t["name"] for t in plan.get("topics", [])] if plan else ["Python"]
    qnum = kwargs.get("question_number", 1)
    idx = min(qnum-1, len(topics)-1) if topics else 0
    return topics[idx] if topics else "Python"

# Simpler mock setup per test
def patch_session_mocks(monkey=None):
    p1 = patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan()))
    p2 = patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda *a, **kw: mock_question(kw.get("question_number",1), _topic_for(kw), "medium", False)))
    p3 = patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval()))
    p4 = patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report()))
    return p1,p2,p3,p4

# --- Actual Tests ---

class TestSessionStart:
    def test_session_start_success(self, client, temp_db):
        now = datetime.now() - timedelta(minutes=1)
        payload = make_payload({
            "scheduled_date": now.strftime("%Y-%m-%d"),
            "scheduled_time": now.strftime("%H:%M"),
            "candidate_name": "SessionStartOK",
        })
        iid = client.post("/api/interviews", json=payload).json()["interview_id"]
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(return_value=mock_question(1, "Introduction"))), \
             patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/start", json={"total_questions": 10})
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert "session_id" in data
            assert data["status"] == "active"
            assert data["question_number"] == 1
            assert "question" in data
            assert data["total_questions"] == 10
            assert data["question"]  # Test 5: first question generated

    def test_session_invalid_interview(self, client, temp_db):
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(return_value=mock_question(1))):
            resp = client.post("/api/interviews/invalid123/session/start", json={"total_questions": 10})
            assert resp.status_code == 404

    def test_session_cannot_start_before_window(self, client, temp_db):
        future = datetime.now() + timedelta(hours=5)
        payload = make_payload({
            "scheduled_date": future.strftime("%Y-%m-%d"),
            "scheduled_time": future.strftime("%H:%M"),
            "candidate_name": "FutureSess",
        })
        iid = client.post("/api/interviews", json=payload).json()["interview_id"]
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(return_value=mock_question(1))):
            resp = client.post(f"/api/interviews/{iid}/session/start", json={"total_questions": 10})
            assert resp.status_code == 400
            assert "not started" in resp.json()["detail"].lower()

    def test_session_cannot_start_after_window(self, client, temp_db):
        past = datetime.now() - timedelta(hours=5)
        payload = make_payload({
            "scheduled_date": past.strftime("%Y-%m-%d"),
            "scheduled_time": past.strftime("%H:%M"),
            "candidate_name": "PastSess",
        })
        iid = client.post("/api/interviews", json=payload).json()["interview_id"]
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(return_value=mock_question(1))):
            resp = client.post(f"/api/interviews/{iid}/session/start", json={"total_questions": 10})
            assert resp.status_code == 400
            assert "ended" in resp.json()["detail"].lower() or "window" in resp.json()["detail"].lower()

    def test_session_invalid_total_questions(self, client, temp_db):
        now = datetime.now() - timedelta(minutes=1)
        payload = make_payload({
            "scheduled_date": now.strftime("%Y-%m-%d"),
            "scheduled_time": now.strftime("%H:%M"),
            "candidate_name": "BadTotal",
        })
        iid = client.post("/api/interviews", json=payload).json()["interview_id"]
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(return_value=mock_question(1))):
            for bad in [4, 31]:
                resp = client.post(f"/api/interviews/{iid}/session/start", json={"total_questions": bad})
                assert resp.status_code == 422 or resp.status_code == 400


class TestSessionAnswer:
    def _create_session(self, client, total=5):
        now = datetime.now() - timedelta(minutes=1)
        payload = make_payload({
            "scheduled_date": now.strftime("%Y-%m-%d"),
            "scheduled_time": now.strftime("%H:%M"),
            "candidate_name": "AnsFlow",
        })
        iid = client.post("/api/interviews", json=payload).json()["interview_id"]
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda **kw: mock_question(kw.get("question_number",1), _topic_for(kw)))), \
             patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/start", json={"total_questions": total})
            assert resp.status_code == 200, resp.text
            data = resp.json()
            return iid, data["session_id"]

    def test_answer_submission(self, client, temp_db):
        iid, sid = self._create_session(client, total=5)
        # Patch again for answer
        with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval(score=8, follow=False))), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda **kw: mock_question(kw.get("question_number"), _topic_for(kw), "hard"))), \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": "I have 5 years in Python and used FAISS for vector search."})
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["status"] == "active"
            assert "question" in data
            assert data["question_number"] == 2  # Test 10: question counter
            assert data["total_questions"] == 5

    def test_answer_evaluation_and_next_question(self, client, temp_db):
        iid, sid = self._create_session(client, total=5)
        # verify evaluation is called and next question generated
        mock_ev = mock_eval(score=7, follow=False)
        with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_ev)) as mock_eval_fn, \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda **kw: mock_question(kw.get("question_number"), _topic_for(kw)))) as mock_q, \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": "Detailed answer about ML."})
            assert resp.status_code == 200
            mock_eval_fn.assert_called_once()
            mock_q.assert_called_once()

    def test_follow_up_logic_strong_answer_increases_difficulty(self, client, temp_db):
        iid, sid = self._create_session(client, total=5)
        # Strong answer => evaluator returns increase, we expect next difficulty hard or follow_up
        strong_eval = mock_eval(score=9, follow=True, diff="increase")
        with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=strong_eval)), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda **kw: mock_question(kw.get("question_number"), _topic_for(kw), "hard", True))) as mock_q, \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": "Strong detailed answer with FAISS comparison and tradeoffs."})
            assert resp.status_code == 200
            data = resp.json()
            # Since we mocked follow_up true, next question should be follow-up or hard
            assert data["difficulty"] == "hard" or data["is_follow_up"] is True

    def test_question_counter_and_max_limit(self, client, temp_db):
        iid, sid = self._create_session(client, total=5)
        # total 5: need 5 answers to complete (q1..q5). Loop 4 active then 1 final.
        for expected_q in [2,3,4,5]:
            is_last = expected_q == 5
            if is_last:
                # Need one more answer after reaching q5 to complete: we are at q4 answers=3? Actually after q4 active we have 3 answers.
                # So we need to answer q5 to complete: that is 4th iteration is not last in count.
                # Our total 5 requires 5 answers: do 4 active iterations then final answer.
                pass
        # redo correctly: 5 answers total
        # We already are at q1, do 4 active answers to reach q5, then final answer to complete
        for exp in [2,3,4,5]:
            with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
                 patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda **kw: mock_question(kw.get("question_number"), _topic_for(kw)))), \
                 patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
                resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": f"Answer {exp}"})
                assert resp.status_code == 200
                if exp < 5:
                    assert resp.json()["question_number"] == exp
                    assert resp.json()["status"] == "active"
                else:
                    # exp 5 still active (now at q5 awaiting answer), need one more to complete
                    assert resp.json()["status"] == "active"
        with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": "Final answer to complete"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "completed"

    def test_session_completion_and_final_report(self, client, temp_db):
        iid, sid = self._create_session(client, total=5)
        # Need 5 answers to complete total=5. Do 4 then final.
        for i in range(4):
            with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
                 patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda **kw: mock_question(kw.get("question_number"), _topic_for(kw)))), \
                 patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
                client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": f"ans {i}"})
        # last
        with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": "final ans"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "completed"
            assert "final_report" in data
            report = data["final_report"]
            assert "overall_score" in report
            assert "recommendation" in report
            assert report["recommendation"] in ["Strong", "Moderate", "Needs Improvement"]

    def test_completed_cannot_accept_answer(self, client, temp_db):
        iid, sid = self._create_session(client, total=5)
        # complete session: need 5 answers
        for _ in range(4):
            with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
                 patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda **kw: mock_question(kw.get("question_number"), _topic_for(kw)))), \
                 patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
                client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": "a"})
        with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": "last"})
        # now try again
        with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())):
            resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": "extra"})
            assert resp.status_code == 400
            assert "completed" in resp.json()["detail"].lower()

    def test_invalid_session_id(self, client, temp_db):
        now = datetime.now() - timedelta(minutes=1)
        payload = make_payload({
            "scheduled_date": now.strftime("%Y-%m-%d"),
            "scheduled_time": now.strftime("%H:%M"),
            "candidate_name": "InvalidSessID",
        })
        iid = client.post("/api/interviews", json=payload).json()["interview_id"]
        # Don't start session, try invalid id
        with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())):
            resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": "nonexistent123", "answer": "hello"})
            assert resp.status_code == 404

    def test_empty_answer_rejected(self, client, temp_db):
        iid, sid = self._create_session(client, total=5)
        resp = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": "   "})
        assert resp.status_code == 422
        assert "empty" in resp.json()["detail"].lower()

    def test_session_end(self, client, temp_db):
        iid, sid = self._create_session(client, total=10)
        with patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/end", json={"session_id": sid})
            assert resp.status_code == 200
            assert resp.json()["status"] == "completed"
            assert "final_report" in resp.json()

    def test_get_session_info(self, client, temp_db):
        iid, sid = self._create_session(client, total=10)
        resp = client.get(f"/api/interviews/{iid}/session")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == sid
        assert data["status"] == "active"
        assert "interview_plan" in data

    def test_session_get_not_found(self, client, temp_db):
        now = datetime.now() - timedelta(minutes=1)
        payload = make_payload({
            "scheduled_date": now.strftime("%Y-%m-%d"),
            "scheduled_time": now.strftime("%H:%M"),
            "candidate_name": "NoSess",
        })
        iid = client.post("/api/interviews", json=payload).json()["interview_id"]
        resp = client.get(f"/api/interviews/{iid}/session")
        assert resp.status_code == 404


class TestMalformedLLMHandling:
    def test_malformed_llm_plan_fallback(self, client, temp_db):
        now = datetime.now() - timedelta(minutes=1)
        payload = make_payload({
            "scheduled_date": now.strftime("%Y-%m-%d"),
            "scheduled_time": now.strftime("%H:%M"),
            "candidate_name": "MalformedPlan",
        })
        iid = client.post("/api/interviews", json=payload).json()["interview_id"]
        # Mock LLM to return malformed JSON, engine should fallback to heuristic
        # patch generate_response to return garbage
        with patch("app.interview.engine.generate_response", new=AsyncMock(return_value=type("obj",(object,),{"response":"NOT JSON ((( "})())):
            resp = client.post(f"/api/interviews/{iid}/session/start", json={"total_questions": 7})
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert "question" in data
            assert data["total_questions"] == 7

    def test_malformed_question_fallback_still_returns(self, client, temp_db):
        now = datetime.now() - timedelta(minutes=1)
        payload = make_payload({
            "scheduled_date": now.strftime("%Y-%m-%d"),
            "scheduled_time": now.strftime("%H:%M"),
            "candidate_name": "MalformedQ",
        })
        iid = client.post("/api/interviews", json=payload).json()["interview_id"]
        # Start normally
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(return_value=mock_question(1))), \
             patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/start", json={"total_questions": 5})
            sid = resp.json()["session_id"]
        # Now mock evaluator to return malformed but still fallback, and question generator to malformed
        with patch("app.interview.evaluator.generate_response", new=AsyncMock(return_value=type("obj",(object,),{"response":"{ broken json"})())):
            # also patch engine question to malformed
            with patch("app.interview.engine.generate_response", new=AsyncMock(return_value=type("obj",(object,),{"response":"garbage not json"})())):
                resp2 = client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": "test answer"})
                # Even with malformed, fallback should allow next question or at least not crash
                assert resp2.status_code == 200, resp2.text
                # Could be completed or active but not 500
                assert resp2.json().get("status") in ["active", "completed"]

    def test_ollama_unavailable_handled(self, client, temp_db):
        now = datetime.now() - timedelta(minutes=1)
        payload = make_payload({
            "scheduled_date": now.strftime("%Y-%m-%d"),
            "scheduled_time": now.strftime("%H:%M"),
            "candidate_name": "OllamaDown",
        })
        iid = client.post("/api/interviews", json=payload).json()["interview_id"]
        from app.services.llm import OllamaError
        async def raise_error(*a, **kw):
            raise OllamaError("Ollama unavailable", 503)
        with patch("app.interview.engine.generate_response", new=AsyncMock(side_effect=raise_error)):
            resp = client.post(f"/api/interviews/{iid}/session/start", json={"total_questions": 5})
            assert resp.status_code == 200, resp.text  # fallback plan should still work
            assert "question" in resp.json()

    def test_llm_helpers_malformed_json_unit(self):
        from app.interview.llm_helpers import extract_json, normalize_evaluation, normalize_question, normalize_plan
        assert extract_json("not json") is None
        assert extract_json('```json\n{"a":1}\n```') == {"a": 1}
        assert extract_json('prefix {"score": 7, "feedback": "ok"} suffix')["score"] == 7
        # trailing comma
        assert extract_json('{"a":1,}')["a"] == 1
        # normalize evaluation
        raw = {"score": 12, "follow_up_needed": "yes"}
        norm = normalize_evaluation(raw)
        assert 0 <= norm["score"] <= 10
        assert isinstance(norm["follow_up_needed"], bool)
        # normalize question fallback
        q = normalize_question({}, 2, fallback_topic="Test")
        assert q["question_number"] == 2
        assert q["topic"] == "Test"
        # normalize plan fallback
        p = normalize_plan({}, "Data Analyst")
        assert len(p["topics"]) >= 5

    def test_final_report_generation_via_end(self, client, temp_db):
        iid, sid = self._create_session_inner(client)
        # answer one then end to generate final report
        with patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval(score=6))), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda **kw: mock_question(kw.get("question_number"), _topic_for(kw)))), \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            client.post(f"/api/interviews/{iid}/session/answer", json={"session_id": sid, "answer": "some answer"})
        with patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/end", json={"session_id": sid})
            assert resp.status_code == 200
            report = resp.json()["final_report"]
            assert "overall_score" in report
            assert "topics_covered" in report
            assert report["recommendation"] in ["Strong", "Moderate", "Needs Improvement"]

    def _create_session_inner(self, client):
        now = datetime.now() - timedelta(minutes=1)
        payload = make_payload({
            "scheduled_date": now.strftime("%Y-%m-%d"),
            "scheduled_time": now.strftime("%H:%M"),
            "candidate_name": "FinalReportTest",
        })
        iid = client.post("/api/interviews", json=payload).json()["interview_id"]
        with patch("app.interview.session_routes.generate_interview_plan", new=AsyncMock(return_value=mock_plan())), \
             patch("app.interview.session_routes.generate_next_question", new=AsyncMock(side_effect=lambda **kw: mock_question(kw.get("question_number",1), _topic_for(kw)))), \
             patch("app.interview.session_routes.evaluate_answer", new=AsyncMock(return_value=mock_eval())), \
             patch("app.interview.session_routes.generate_final_report", new=AsyncMock(return_value=mock_report())):
            resp = client.post(f"/api/interviews/{iid}/session/start", json={"total_questions": 5})
            sid = resp.json()["session_id"]
            return iid, sid

    def test_inconsistency_detection(self):
        from app.interview.evaluator import _detect_inconsistency
        note = _detect_inconsistency("I have never worked with Python", "Resume: Python, FastAPI, ML")
        assert note is not None
        assert "inconsistency" in note.lower()
        # no flag when consistent
        note2 = _detect_inconsistency("I love working with Python", "Resume: Python")
        assert note2 is None

    def test_plan_varies_by_role(self):
        import asyncio
        from app.interview.engine import _heuristic_plan
        plan_da = _heuristic_plan("Data Analyst needs SQL Tableau", "Resume with SQL", "Data Analyst")
        names_da = [t["name"] for t in plan_da["topics"]]
        assert any("SQL" in n for n in names_da)
        plan_hr = _heuristic_plan("HR role needs communication", "Resume HR", "HR Manager")
        names_hr = [t["name"] for t in plan_hr["topics"]]
        assert any("HR" in n or "Communication" in n for n in names_hr)
        assert plan_da != plan_hr
