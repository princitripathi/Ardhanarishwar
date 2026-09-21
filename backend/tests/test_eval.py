"""Tests for Phase 1 evaluation framework — no behavior change to orchestrator/agents."""

import pytest
import asyncio

from eval.dataset import DATASET, EDGE_CASES, CONTEXT_CASES, validate_dataset
from eval.runner import (
    score_relevance,
    score_completeness,
    detect_hallucination,
    detect_error_signal,
    check_context_awareness,
    evaluate_routing_only,
    evaluate_single_case,
    evaluate_all,
    _word_count,
)


# --- Dataset integrity ---

def test_dataset_covers_all_domains():
    domains = {c["domain"] for c in DATASET}
    assert domains == {"career", "resume", "interview", "learning", "recruitment", "business", "general"}
    # At least 5 per domain
    for d in domains:
        assert sum(1 for c in DATASET if c["domain"] == d) >= 5
    # Total single dataset 35
    assert len(DATASET) == 35


def test_dataset_ids_unique():
    ids = [c["id"] for c in DATASET]
    assert len(ids) == len(set(ids))
    edge_ids = [c["id"] for c in EDGE_CASES]
    assert len(edge_ids) == len(set(edge_ids))
    assert not set(ids) & set(edge_ids)


def test_dataset_messages_nonempty():
    for c in DATASET:
        assert c["message"] and c["message"].strip()
        assert "domain" in c
        assert "expected_keywords" in c


def test_validate_dataset_counts():
    counts = validate_dataset()
    assert counts["career"] == 5
    assert counts["general"] == 5
    assert sum(counts.values()) == 35


def test_context_cases_structure():
    assert len(CONTEXT_CASES) == 3
    for seq in CONTEXT_CASES:
        assert "conversation_id" in seq
        assert "turns" in seq and len(seq["turns"]) >= 2
        for turn in seq["turns"]:
            assert "message" in turn and "expected" in turn


def test_edge_cases_include_probes():
    # At least 3 hallucination probes with forbidden_phrases
    probes = [c for c in EDGE_CASES if c.get("forbidden_phrases")]
    assert len(probes) >= 3


# --- Heuristic units ---

def test_score_relevance():
    resp = "This is career advice about growth and planning for your career"
    r = score_relevance(resp, ["career", "growth", "python"])
    assert r["score"] == pytest.approx(2 / 3, abs=0.01)
    assert "career" in r["matched"]

    r2 = score_relevance(resp, [])
    assert r2["score"] is None

    r3 = score_relevance("", ["career"])
    assert r3["score"] == 0


def test_score_completeness():
    short = "hi"
    c = score_completeness(short, min_words=20)
    assert c["passed"] is False
    assert c["word_count"] == 1

    good = "Here is a good answer. It has multiple sentences. With bullet points:\n- item one\n- item two"
    c2 = score_completeness(good, min_words=10)
    assert c2["passed"] is True
    assert c2["has_bullets_or_list"] is True
    assert c2["sentence_count"] >= 2


def test_detect_hallucination():
    resp = "I have access to live job listings and fetched the latest jobs for you."
    h = detect_hallucination(resp)
    assert h["hallucination_flag"] is True
    assert len(h["matched_phrases"]) >= 1

    clean = "I can give general career advice based on best practices. I don't have live browsing."
    h2 = detect_hallucination(clean)
    assert h2["hallucination_flag"] is False

    # Custom forbidden
    h3 = detect_hallucination("your ATS score is 87/100", forbidden=["your ats score is"])
    assert h3["hallucination_flag"] is True


def test_detect_error_signal():
    e = detect_error_signal("", None)
    assert e["error_flag"] is True
    assert "empty_response" in e["matched"]

    e2 = detect_error_signal("Ollama is unavailable", None)
    assert e2["error_flag"] is True

    e3 = detect_error_signal("This is a normal helpful answer with enough words.", None)
    assert e3["error_flag"] is False


def test_check_context_awareness():
    c = check_context_awareness("This builds on Generative AI context", "Generative AI")
    assert c["passed"] is True

    c2 = check_context_awareness("No mention here", "Generative AI")
    assert c2["passed"] is False

    c3 = check_context_awareness("irrelevant", None)
    assert c3["checked"] is False


def test_word_count():
    assert _word_count("") == 0
    assert _word_count("  hello   world  ") == 2


# --- Routing (no LLM) ---

def test_evaluate_routing_only_all_domains_present():
    report = evaluate_routing_only()
    assert "overall_accuracy" in report
    assert 0 <= report["overall_accuracy"] <= 1
    assert report["total"] >= 39  # 35 + 4 edge non-skipped
    # Should have per-domain entries
    assert "career" in report["per_domain"]
    assert "general" in report["per_domain"]
    # Routing should be reasonably good — but we don't require 100% (ambiguous edge)
    assert report["overall_accuracy"] >= 0.85, f"Routing degraded: {report}"


def test_routing_only_details_correctness():
    report = evaluate_routing_only()
    # Each detail should have correct flag consistent with actual vs expected
    for d in report["details"]:
        if "acceptable" in d:
            assert d["correct"] == (d["actual"] in d["acceptable"])
        else:
            assert d["correct"] == (d["actual"] == d["expected"])


# --- Async single case with mock ---

def test_evaluate_single_case_mock_routing_correct():
    case = {"id": "test-career", "domain": "career", "message": "Help me plan my career", "expected_keywords": ["career"]}
    res = asyncio.run(evaluate_single_case(case, conversation_id="test-mock-correct", mock_response="Career advice: plan your growth with career steps"))
    assert res.routing_correct is True
    assert res.actual_intent == "career"
    assert res.latency_ms is not None and res.latency_ms >= 0
    assert res.relevance["score"] is not None
    assert res.needs_human_review is True
    assert res.hallucination["hallucination_flag"] is False
    assert res.error_signal["error_flag"] is False


def test_evaluate_single_case_mock_hallucination_flag():
    case = {
        "id": "edge-test",
        "domain": "general",
        "message": "Do you have live jobs?",
        "expected_keywords": [],
        "forbidden_phrases": ["i have access to live job listings"],
    }
    res = asyncio.run(evaluate_single_case(case, mock_response="I have access to live job listings and fetched them"))
    assert res.hallucination["hallucination_flag"] is True


def test_evaluate_all_mock():
    # Run small subset mocked
    small = DATASET[:4]
    report = asyncio.run(evaluate_all(cases=small, use_mock=True, include_context_cases=False))
    assert report["summary"]["total"] == 4
    assert report["summary"]["mode"] == "mock"
    assert "routing_accuracy" in report["summary"]
    assert "latency" in report["summary"]
    assert len(report["results"]) == 4


def test_evaluate_all_mock_includes_context():
    report = asyncio.run(evaluate_all(use_mock=True))
    # Full default: 35 +4 +6 =45
    assert report["summary"]["total"] == 45
    assert report["summary"]["context_results"] == 6
    assert report["summary"]["routing_accuracy"] >= 0.8
    assert report["summary"]["latency"]["mean_ms"] is not None


def test_evaluate_all_mock_does_not_modify_orchestrator_behavior():
    # Ensure after evaluation, orchestrator still works normally (clear state)
    from app.services.orchestrator import detect_intent

    asyncio.run(evaluate_all(use_mock=True))
    # Business-as-usual routing unaffected
    assert detect_intent("Help me plan my career growth") == "career"
    # Eval cleaned up its context cids? At least not broken.
    # We check eval-ctx ids were used and cleared for next run (second run should still pass)
    report2 = asyncio.run(evaluate_all(use_mock=True))
    assert report2["summary"]["routing_accuracy"] >= 0.8


def test_evaluate_all_sync_wrapper():
    # Ensure pytest can run async via asyncio.run path used by CLI
    import asyncio
    report = asyncio.run(evaluate_all(use_mock=True, cases=DATASET[:2], include_context_cases=False))
    assert report["summary"]["total"] == 2
