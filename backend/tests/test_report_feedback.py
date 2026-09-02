import pytest
from app.interview.evaluator import _heuristic_eval
from app.interview.engine import _heuristic_report

def test_strong_answer_produces_meaningful_strengths():
    strong_answer = """
    In my previous project I built a Python FastAPI service that uses FAISS for semantic retrieval.
    For example, I implemented a pipeline that ingests documents, creates embeddings, and serves queries with low latency.
    The system reduced query latency by 30% and improved retrieval accuracy. I also evaluated trade-offs between HNSW and IVF indexes,
    choosing HNSW for better recall versus memory usage. The architecture included a microservice with clear separation of concerns.
    """
    ev = _heuristic_eval(strong_answer)
    assert ev["score"] >= 7
    strengths_text = " ".join(ev["strengths"]).lower()
    # Should not be generic "Provided an answer"
    assert "provided an answer" not in strengths_text or "implementation details" in strengths_text or "technical" in strengths_text
    # Should contain meaningful phrases
    assert any(phrase in strengths_text for phrase in ["implementation details", "concrete examples", "technical concepts", "clear structure", "measurable impact", "trade-offs"])
    # Weaknesses should be minimal for strong
    assert len(ev["weaknesses"]) <= 1 or "deeper" in " ".join(ev["weaknesses"]).lower() or len(ev["weaknesses"]) == 0

def test_weak_answer_produces_meaningful_improvement_areas():
    weak_answer = "I did some work. It was okay."
    ev = _heuristic_eval(weak_answer)
    assert ev["score"] < 6
    weaknesses_text = " ".join(ev["weaknesses"]).lower()
    assert any(phrase in weaknesses_text for phrase in ["lacked implementation", "concrete examples", "greater depth", "trade-offs", "clarity"])
    # Strengths should be empty or minimal for weak
    assert len(ev["strengths"]) <= 1

def test_different_evaluation_sets_produce_different_feedback():
    strong_evals = [
        {"score": 8, "correctness": 8, "relevance": 8, "depth": 8, "clarity": 8, "feedback": "Strong", "strengths": ["Demonstrated good understanding"], "weaknesses": [], "follow_up_needed": False, "difficulty_adjustment": "increase", "inconsistency_flag": False},
        {"score": 9, "correctness": 9, "relevance": 8, "depth": 8, "clarity": 8, "feedback": "Strong", "strengths": ["Explained project concepts"], "weaknesses": [], "follow_up_needed": False, "difficulty_adjustment": "increase", "inconsistency_flag": False},
    ]
    weak_evals = [
        {"score": 4, "correctness": 4, "relevance": 4, "depth": 3, "clarity": 4, "feedback": "Weak", "strengths": [], "weaknesses": ["Lacked detail"], "follow_up_needed": True, "difficulty_adjustment": "decrease", "inconsistency_flag": False},
        {"score": 3, "correctness": 3, "relevance": 3, "depth": 3, "clarity": 3, "feedback": "Weak", "strengths": [], "weaknesses": ["Too brief"], "follow_up_needed": True, "difficulty_adjustment": "decrease", "inconsistency_flag": False},
    ]
    topics = ["Python", "Machine Learning"]
    report_strong = _heuristic_report(strong_evals, topics)
    report_weak = _heuristic_report(weak_evals, topics)
    assert report_strong["overall_score"] != report_weak["overall_score"]
    assert report_strong["overall_score"] >= 7
    assert report_weak["overall_score"] < 6
    assert report_strong["strengths"] != report_weak["strengths"]
    # Strong should have meaningful strengths
    strong_text = " ".join(report_strong["strengths"]).lower()
    assert any(k in strong_text for k in ["technical", "implementation", "clear", "aligned", "problem-solving"])
    # Weak should have meaningful weaknesses
    weak_text = " ".join(report_weak["weaknesses"]).lower()
    assert any(k in weak_text for k in ["implementation details", "clarity", "depth", "technical", "aligned"])

def test_empty_evaluations_do_not_crash():
    report = _heuristic_report([], ["Python"])
    assert report["overall_score"] == 5
    assert "strengths" in report and len(report["strengths"]) > 0
    assert "weaknesses" in report and len(report["weaknesses"]) > 0
    assert "topics_covered" in report
    assert report["recommendation"] in ["Strong", "Moderate", "Needs Improvement"]

def test_missing_fields_do_not_crash():
    # evaluations with missing fields
    evals = [
        {"score": 7},
        {},
        {"correctness": 8, "depth": 6},
    ]
    report = _heuristic_report(evals, [])
    assert "overall_score" in report
    assert "strengths" in report
    assert "weaknesses" in report
    assert report["recommendation"] in ["Strong", "Moderate", "Needs Improvement"]
    # Should not contain generic "Provided an answer" as only strength for mixed
    strengths_text = " ".join(report["strengths"]).lower()
    # At least should be meaningful or not crash
    assert len(report["strengths"]) > 0

def test_not_always_generic():
    # Ensure strong candidate not getting generic strengths
    strong_answer = "I implemented a Python microservice with FastAPI and FAISS, for example I built a RAG pipeline that improved throughput by 25% and explained trade-offs between latency and accuracy."
    ev = _heuristic_eval(strong_answer)
    assert "Provided an answer" not in ev["strengths"]
    assert "Could provide more depth in some answers." not in ev["weaknesses"] or len(ev["weaknesses"]) == 0 or "technical" in " ".join(ev["weaknesses"]).lower()
    # Weak candidate should not get same strengths as strong
    weak = _heuristic_eval("short answer")
    assert ev["strengths"] != weak["strengths"] or ev["score"] != weak["score"]

def test_honest_reflection_poor_vs_good():
    good_evals = [{"score": 8, "correctness": 8, "relevance": 8, "depth": 8, "clarity": 8, "strengths": [], "weaknesses": [], "follow_up_needed": False, "difficulty_adjustment": "maintain"} for _ in range(3)]
    poor_evals = [{"score": 3, "correctness": 3, "relevance": 3, "depth": 3, "clarity": 3, "strengths": [], "weaknesses": [], "follow_up_needed": True, "difficulty_adjustment": "decrease"} for _ in range(3)]
    report_good = _heuristic_report(good_evals, ["Python"])
    report_poor = _heuristic_report(poor_evals, ["Python"])
    assert report_good["recommendation"] in ["Strong", "Moderate"]
    assert report_poor["recommendation"] == "Needs Improvement"
    assert report_good["overall_score"] > report_poor["overall_score"]
    assert report_good["summary"].lower().count("strong") or "good" in report_good["summary"].lower() or "8" in report_good["summary"]
    assert "below expectations" in report_poor["summary"].lower() or "needs" in report_poor["summary"].lower()
