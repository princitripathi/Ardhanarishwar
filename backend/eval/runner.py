"""Lightweight evaluation runner for Ardhanarishwar Solver.

Measures:
- intent routing (vs expected)
- response relevance / completeness / context awareness (heuristics)
- hallucination/error signals (reasonably detectable, substring checks)
- latency

Does NOT claim automated score is ground truth. Each heuristic is documented
with limitations and requires human review.

Usage:
    python -m eval.runner --mock          # offline, no Ollama needed
    python -m eval.runner                 # live, hits Ollama via orchestrator
    python -m eval.runner --mock --output results.json
"""

import asyncio
import time
import json
import re
import statistics
import argparse
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from collections import Counter, defaultdict

from eval.dataset import DATASET, EDGE_CASES, CONTEXT_CASES

# Hallucination signal phrases — responses should NOT contain these verbatim
# (case-insensitive substring). These cover disallowed claims observed in prompts.
DEFAULT_FORBIDDEN_PHRASES = [
    "i have access to live job listings",
    "i fetched the latest jobs",
    "here are live jobs",
    "i browsed the internet",
    "according to today's news i fetched",
    "your ats score is",
    "i can access proprietary resume databases",
    "i have real-time browsing",
]

# What we flag as error signals in responses
ERROR_SIGNAL_PATTERNS = [
    r"ollama.*unavailable",
    r"failed to connect",
    r"\b500\b.*error",
    r"empty response from model",
]


def _word_count(text: str) -> int:
    return len(text.strip().split()) if text and text.strip() else 0


def score_relevance(response: str, expected_keywords: List[str]) -> Dict[str, Any]:
    """Heuristic relevance: fraction of expected_keywords found (case-insensitive)."""
    if not expected_keywords:
        return {"score": None, "matched": [], "total": 0, "note": "no keywords defined"}
    lower = (response or "").lower()
    matched = [kw for kw in expected_keywords if kw.lower() in lower]
    score = len(matched) / len(expected_keywords) if expected_keywords else 0
    return {"score": round(score, 2), "matched": matched, "total": len(expected_keywords)}


def score_completeness(response: str, min_words: int = 20) -> Dict[str, Any]:
    """Heuristic completeness: word/sentence counts, basic structure."""
    wc = _word_count(response)
    sentences = max(1, response.count(".") + response.count("!") + response.count("?")) if response else 0
    has_bullets = bool(re.search(r"^(\s*[-*•]|\s*\d+\.)\s+", response or "", re.MULTILINE))
    # No LLM judging — just length/structure proxies
    passed = wc >= min_words
    return {
        "word_count": wc,
        "sentence_count": sentences,
        "has_bullets_or_list": has_bullets,
        "min_words": min_words,
        "passed": passed,
    }


def detect_hallucination(response: str, forbidden: Optional[List[str]] = None) -> Dict[str, Any]:
    """Check response for forbidden hallucination phrases."""
    lower = (response or "").lower()
    phrases = forbidden or DEFAULT_FORBIDDEN_PHRASES
    found = [p for p in phrases if p.lower() in lower]
    return {"hallucination_flag": len(found) > 0, "matched_phrases": found}


def detect_error_signal(response: str, detail: Optional[str] = None) -> Dict[str, Any]:
    """Detect obvious error/ollama signals in response or detail string."""
    text = f"{response or ''} {detail or ''}".lower()
    matched = []
    for pat in ERROR_SIGNAL_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            matched.append(pat)
    # Also flag empty or extremely short
    if not response or not response.strip():
        matched.append("empty_response")
    elif _word_count(response) < 3:
        matched.append("too_short")
    return {"error_flag": len(matched) > 0, "matched": matched}


def check_context_awareness(response: str, context_check: Optional[str]) -> Dict[str, Any]:
    """For context cases: does response mention prior context keyword?"""
    if not context_check:
        return {"checked": False, "passed": None, "note": "no context_check defined"}
    lower = (response or "").lower()
    passed = context_check.lower() in lower
    return {"checked": True, "context_keyword": context_check, "passed": passed}


def _safe_intent_call(message: str) -> str:
    from app.services.orchestrator import detect_intent
    return detect_intent(message)


def _safe_context_intent(message: str, history: List[Dict[str, str]], conversation_id: str) -> str:
    from app.services.orchestrator import _detect_with_context
    return _detect_with_context(message, history, conversation_id)


def evaluate_routing_only() -> Dict[str, Any]:
    """Fast offline check: routing accuracy without LLM calls."""
    per_domain = defaultdict(lambda: {"correct": 0, "total": 0})
    details = []
    # Single dataset
    for case in DATASET:
        actual = _safe_intent_call(case["message"])
        expected = case["domain"]
        correct = actual == expected
        per_domain[expected]["total"] += 1
        if correct:
            per_domain[expected]["correct"] += 1
        details.append(
            {
                "id": case["id"],
                "expected": expected,
                "actual": actual,
                "correct": correct,
                "message": case["message"][:80],
            }
        )
    # Edge (skip empty)
    for case in EDGE_CASES:
        if case.get("skip_routing"):
            continue
        acceptable = case.get("acceptable_intents") or [case["domain"]]
        actual = _safe_intent_call(case["message"])
        correct = actual in acceptable
        # count under edge domain
        per_domain[case["domain"]]["total"] += 1
        if correct:
            per_domain[case["domain"]]["correct"] += 1
        details.append(
            {
                "id": case["id"],
                "expected": case["domain"],
                "acceptable": acceptable,
                "actual": actual,
                "correct": correct,
                "message": case["message"][:80],
            }
        )
    total_correct = sum(v["correct"] for v in per_domain.values())
    total = sum(v["total"] for v in per_domain.values())
    per_domain_pct = {k: round(v["correct"] / v["total"], 2) if v["total"] else 0 for k, v in per_domain.items()}
    return {
        "mode": "routing_only",
        "overall_accuracy": round(total_correct / total, 3) if total else 0,
        "total_correct": total_correct,
        "total": total,
        "per_domain": dict(per_domain),
        "per_domain_accuracy": per_domain_pct,
        "details": details,
    }


@dataclass
class SingleResult:
    id: str
    domain: str
    message: str
    expected_intent: str
    actual_intent: str
    routing_correct: bool
    routing_reason: Optional[str]
    latency_ms: Optional[float]
    response: Optional[str]
    response_word_count: int
    relevance: Dict[str, Any]
    completeness: Dict[str, Any]
    hallucination: Dict[str, Any]
    error_signal: Dict[str, Any]
    context_check: Dict[str, Any]
    error_detail: Optional[str] = None
    needs_human_review: bool = True


async def _call_orchestrator(message: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """Call route_message and return its dict; mock-safe."""
    from app.services.orchestrator import route_message
    return await route_message(message, conversation_id=conversation_id)


async def evaluate_single_case(case: Dict, conversation_id: Optional[str] = None, mock_response: Optional[str] = None) -> SingleResult:
    """Evaluate one case end-to-end (routing + response heuristics)."""
    expected = case["domain"]
    msg = case["message"]
    # If mock_response supplied, patch generate_response to avoid Ollama
    start = time.perf_counter()
    error_detail = None
    result = None
    response_text = None
    actual_intent = None
    routing_reason = None
    cid_used = None
    try:
        if mock_response is not None:
            from unittest.mock import AsyncMock, patch

            mock_ret = type("obj", (), {"response": mock_response, "model": "qwen2.5:3b"})()
            # Patch both orchestrator paths: general and agent generate_response
            with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_ret)), \
                 patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock_ret)), \
                 patch("app.agents.resume_agent.generate_response", new=AsyncMock(return_value=mock_ret)), \
                 patch("app.agents.interview_agent.generate_response", new=AsyncMock(return_value=mock_ret)), \
                 patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock_ret)), \
                 patch("app.agents.recruitment_agent.generate_response", new=AsyncMock(return_value=mock_ret)), \
                 patch("app.agents.business_agent.generate_response", new=AsyncMock(return_value=mock_ret)):
                result = await _call_orchestrator(msg, conversation_id=conversation_id)
        else:
            result = await _call_orchestrator(msg, conversation_id=conversation_id)
        latency_ms = (time.perf_counter() - start) * 1000
        response_text = result.get("response", "")
        actual_intent = result.get("intent", "")
        routing_reason = result.get("routing_reason")
        cid_used = result.get("conversation_id")
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        # Try to extract OllamaError detail if present
        error_detail = str(getattr(e, "message", str(e)))
        # Still record routing via detect_intent so routing metric not blocked by Ollama
        try:
            actual_intent = _safe_intent_call(msg)
        except Exception:
            actual_intent = "unknown"
        response_text = ""

    routing_correct = False
    acceptable = case.get("acceptable_intents") or [expected]
    if actual_intent in acceptable:
        routing_correct = True

    # Heuristics on response (even if empty, report signals)
    forbidden = case.get("forbidden_phrases") or None
    return SingleResult(
        id=case["id"],
        domain=case["domain"],
        message=msg,
        expected_intent=expected,
        actual_intent=actual_intent or "unknown",
        routing_correct=routing_correct,
        routing_reason=routing_reason,
        latency_ms=round(latency_ms, 1) if latency_ms is not None else None,
        response=response_text,
        response_word_count=_word_count(response_text or ""),
        relevance=score_relevance(response_text or "", case.get("expected_keywords", [])),
        completeness=score_completeness(response_text or "", min_words=20),
        hallucination=detect_hallucination(response_text or "", forbidden),
        error_signal=detect_error_signal(response_text or "", error_detail),
        context_check=check_context_awareness(response_text or "", case.get("context_check")),
        error_detail=error_detail,
        needs_human_review=True,
    )


async def evaluate_all(
    cases: Optional[List[Dict]] = None,
    use_mock: bool = False,
    mock_response_template: Optional[str] = None,
    include_context_cases: bool = True,
) -> Dict[str, Any]:
    """Run full evaluation across dataset."""
    if cases is None:
        cases = list(DATASET) + [c for c in EDGE_CASES if not c.get("skip_routing")]
    # For mock mode, build a domain-aware mock response
    def mock_for_case(c):
        if mock_response_template:
            return mock_response_template
        # Simple templated mock that will satisfy keyword checks
        kws = " ".join(c.get("expected_keywords", [])[:3])
        return f"Mock response for {c['domain']} about {c['message'][:40]}. Keywords: {kws}. This is a helpful answer with bullet points:\n- Point one about {c['domain']}\n- Point two with guidance."

    results: List[SingleResult] = []
    for case in cases:
        mock_resp = mock_for_case(case) if use_mock else None
        # Use a unique conversation_id per case to avoid cross-contamination unless context case
        cid = case.get("conversation_id") or f"eval-{case['id']}"
        res = await evaluate_single_case(case, conversation_id=cid, mock_response=mock_resp)
        results.append(res)

    context_results = []
    if include_context_cases:
        for seq in CONTEXT_CASES:
            cid = seq["conversation_id"]
            # Need to clear memory between sequences (orchestrator state)
            from app.services import conversation_memory as cm
            from app.services.orchestrator import _last_intent
            cm.clear_conversation(cid)
            _last_intent.pop(cid, None)
            for turn in seq["turns"]:
                fake_case = {
                    "id": f"{seq['id']}-turn-{turn['expected']}",
                    "domain": turn["expected"],
                    "message": turn["message"],
                    "expected_keywords": [],
                    "context_check": turn.get("context_check"),
                }
                mock_resp = None
                if use_mock:
                    # Include context_check keyword in mock so context heuristic passes
                    ctx_kw = turn.get("context_check", "")
                    mock_resp = f"Mock follow-up for {turn['expected']}. Context includes {ctx_kw}. Helpful answer."
                res = await evaluate_single_case(fake_case, conversation_id=cid, mock_response=mock_resp)
                # annotate with sequence id
                res.id = f"{seq['id']}|{turn['message'][:30]}"
                context_results.append(res)
                results.append(res)

    # Aggregates
    total = len(results)
    correct = sum(1 for r in results if r.routing_correct)
    latencies = [r.latency_ms for r in results if r.latency_ms is not None]
    halluc_flags = sum(1 for r in results if r.hallucination.get("hallucination_flag"))
    error_flags = sum(1 for r in results if r.error_signal.get("error_flag"))
    relevance_scores = [r.relevance.get("score") for r in results if r.relevance.get("score") is not None]
    completeness_pass = sum(1 for r in results if r.completeness.get("passed"))

    per_domain = Counter()
    per_domain_correct = Counter()
    for r in results:
        per_domain[r.expected_intent] += 1
        if r.routing_correct:
            per_domain_correct[r.expected_intent] += 1

    per_domain_acc = {k: round(per_domain_correct[k] / per_domain[k], 2) if per_domain[k] else 0 for k in per_domain}

    summary = {
        "mode": "mock" if use_mock else "live",
        "total_cases": total,
        "routing_accuracy": round(correct / total, 3) if total else 0,
        "correct": correct,
        "total": total,
        "per_domain": dict(per_domain),
        "per_domain_accuracy": per_domain_acc,
        "latency": {
            "mean_ms": round(statistics.mean(latencies), 1) if latencies else None,
            "median_ms": round(statistics.median(latencies), 1) if latencies else None,
            "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)] , 1) if latencies else None,
            "min_ms": round(min(latencies), 1) if latencies else None,
            "max_ms": round(max(latencies), 1) if latencies else None,
        },
        "hallucination_flags": halluc_flags,
        "error_flags": error_flags,
        "relevance_mean": round(statistics.mean(relevance_scores), 2) if relevance_scores else None,
        "completeness_pass": completeness_pass,
        "completeness_pass_rate": round(completeness_pass / total, 2) if total else 0,
        "context_results": len(context_results),
        "note": "Automated heuristics are NOT ground truth. Human review required for relevance/completeness/hallucination.",
    }

    # Serializable results
    serialized = [asdict(r) for r in results]

    return {"summary": summary, "results": serialized, "context_details": [asdict(r) for r in context_results]}


def print_summary(report: Dict[str, Any]) -> None:
    s = report["summary"]
    print("\n=== Ardhanarishwar Solver Evaluation Summary ===")
    print(f"Mode: {s['mode']} | Total: {s['total']} | Routing accuracy: {s['routing_accuracy']} ({s['correct']}/{s['total']})")
    print("Per-domain accuracy:")
    for dom, acc in sorted(s["per_domain_accuracy"].items()):
        print(f"  {dom:12s}: {acc:.2f}  (n={s['per_domain'][dom]})")
    lat = s["latency"]
    print(f"Latency (ms): mean={lat['mean_ms']} median={lat['median_ms']} p95={lat['p95_ms']} min={lat['min_ms']} max={lat['max_ms']}")
    print(f"Relevance mean (keyword recall): {s['relevance_mean']}  | Completeness pass (>=20 words): {s['completeness_pass']}/{s['total']} ({s['completeness_pass_rate']})")
    print(f"Hallucination flags: {s['hallucination_flags']} | Error flags: {s['error_flags']} | Context cases: {s['context_results']}")
    print("Note: " + s["note"])
    # Show failures
    fails = [r for r in report["results"] if not r["routing_correct"]]
    if fails:
        print("\nRouting failures (human review candidates):")
        for r in fails[:10]:
            print(f"  {r['id']:18s} expected={r['expected_intent']:12s} actual={r['actual_intent']:12s} msg=\"{r['message'][:60]}\"")
    hallucs = [r for r in report["results"] if r["hallucination"]["hallucination_flag"]]
    if hallucs:
        print("\nHallucination flags:")
        for r in hallucs:
            print(f"  {r['id']}: {r['hallucination']['matched_phrases']}")
    errors = [r for r in report["results"] if r["error_signal"]["error_flag"]]
    if errors:
        print("\nError signals:")
        for r in errors[:10]:
            print(f"  {r['id']}: {r['error_signal']['matched']} detail={r['error_detail']}")


def main():
    parser = argparse.ArgumentParser(description="Ardhanarishwar Solver evaluation runner")
    parser.add_argument("--mock", action="store_true", help="Use mocked LLM responses (offline, no Ollama)")
    parser.add_argument("--output", type=str, default=None, help="Write JSON report to file")
    parser.add_argument("--routing-only", action="store_true", help="Only test intent routing (fastest, no LLM)")
    args = parser.parse_args()

    if args.routing_only:
        rep = evaluate_routing_only()
        print(json.dumps(rep, indent=2))
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(rep, f, indent=2)
            print(f"\nWrote routing report to {args.output}")
        return

    report = asyncio.run(evaluate_all(use_mock=args.mock))
    print_summary(report)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nWrote report to {args.output}")


if __name__ == "__main__":
    main()
