import json
import re
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Safely extract JSON from LLM response.
    Tries: direct parse, code block extraction, regex for outermost {}.
    Returns dict or None on failure.
    """
    if not text:
        return None
    text = text.strip()
    # direct
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # strip code fences
    # remove ```json ... ```
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    # find outermost JSON object via balanced braces heuristic
    # simplest: find first { and last } slice
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        # try to fix trailing commas
        candidate2 = re.sub(r",\s*}", "}", candidate)
        candidate2 = re.sub(r",\s*]", "]", candidate2)
        try:
            return json.loads(candidate2)
        except json.JSONDecodeError:
            pass

    # try json array? but we expect object
    return None


def safe_json_parse_with_fallback(text: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    data = extract_json(text)
    if data is None:
        logger.warning(f"Failed to parse LLM JSON, using fallback. Raw: {text[:500]}")
        return fallback
    return data


def clamp_score(v: Any, default: int = 5) -> int:
    try:
        iv = int(round(float(v)))
        return max(0, min(10, iv))
    except Exception:
        return default


def normalize_evaluation(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure evaluator output has required fields and sane values."""
    if not isinstance(raw, dict):
        raw = {}
    out = {}
    out["score"] = clamp_score(raw.get("score", 5))
    out["correctness"] = clamp_score(raw.get("correctness", out["score"]))
    out["relevance"] = clamp_score(raw.get("relevance", out["score"]))
    out["depth"] = clamp_score(raw.get("depth", out["score"]))
    out["clarity"] = clamp_score(raw.get("clarity", out["score"]))
    out["feedback"] = str(raw.get("feedback", "Answer evaluated."))[:500] if raw.get("feedback") else "Answer evaluated."
    strengths = raw.get("strengths") or []
    if not isinstance(strengths, list):
        strengths = [str(strengths)]
    out["strengths"] = [str(s)[:200] for s in strengths][:3]
    weaknesses = raw.get("weaknesses") or []
    if not isinstance(weaknesses, list):
        weaknesses = [str(weaknesses)]
    out["weaknesses"] = [str(s)[:200] for s in weaknesses][:3]
    out["follow_up_needed"] = bool(raw.get("follow_up_needed", False))
    out["inconsistency_flag"] = bool(raw.get("inconsistency_flag", False))
    note = raw.get("inconsistency_note")
    out["inconsistency_note"] = str(note)[:300] if note else None
    if out["inconsistency_flag"] and not out["inconsistency_note"]:
        out["inconsistency_note"] = "Potential inconsistency between the candidate's answer and resume."
    adj = str(raw.get("difficulty_adjustment", "maintain")).lower()
    if adj not in ("increase", "decrease", "maintain"):
        adj = "maintain"
    out["difficulty_adjustment"] = adj
    return out


def normalize_question(raw: Dict[str, Any], question_number: int, fallback_topic: str = "General") -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    q_text = raw.get("question") or raw.get("text") or ""
    q_text = str(q_text).strip()
    if not q_text or len(q_text) < 5:
        q_text = f"Could you elaborate more on your experience relevant to {fallback_topic}?"
    topic = str(raw.get("topic", fallback_topic)).strip() or fallback_topic
    diff = str(raw.get("difficulty", "medium")).lower()
    if diff not in ("easy", "medium", "hard"):
        diff = "medium"
    expected = str(raw.get("expected_focus", raw.get("expectedFocus", "Clear and relevant answer"))).strip() or "Clear and relevant answer"
    is_follow = bool(raw.get("is_follow_up", False))
    return {
        "question": q_text,
        "topic": topic,
        "difficulty": diff,
        "question_number": question_number,
        "expected_focus": expected[:300],
        "is_follow_up": is_follow,
    }


def normalize_plan(raw: Dict[str, Any], job_title: str) -> Dict[str, Any]:
    """Normalize plan to have topics list."""
    topics = None
    if isinstance(raw, dict):
        topics = raw.get("topics") or raw.get("plan") or raw.get("interview_plan")
    if not isinstance(topics, list) or len(topics) == 0:
        # heuristic fallback
        topics = [
            {"name": "Introduction", "focus": "Candidate background and motivation"},
            {"name": "Resume & Projects", "focus": "Discussion of resume and key projects"},
            {"name": job_title or "Role Fundamentals", "focus": f"Core knowledge for {job_title}"},
            {"name": "Technical Skills", "focus": "Required technical abilities"},
            {"name": "Problem Solving", "focus": "Approach to challenges"},
            {"name": "Behavioral & Communication", "focus": "Teamwork and communication"},
            {"name": "Candidate Questions", "focus": "Questions from candidate"},
        ]
    normalized = []
    seen = set()
    for t in topics:
        if isinstance(t, str):
            name = t.strip()
            focus = ""
        elif isinstance(t, dict):
            name = str(t.get("name") or t.get("topic") or t.get("title") or "").strip()
            focus = str(t.get("focus") or t.get("description") or "").strip()
        else:
            continue
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        normalized.append({"name": name, "focus": focus or f"Assess {name}"})
    # ensure first is Introduction
    if normalized and normalized[0]["name"].lower() != "introduction":
        normalized.insert(0, {"name": "Introduction", "focus": "Candidate background and motivation"})
    # cap 7-10
    if len(normalized) > 10:
        normalized = normalized[:10]
    if len(normalized) < 5:
        # pad with generic
        for extra in ["Problem Solving", "Behavioral & Communication"]:
            if len(normalized) >= 7:
                break
            if extra.lower() not in seen:
                normalized.append({"name": extra, "focus": f"Assess {extra}"})
    return {"topics": normalized}


def normalize_final_report(raw: Dict[str, Any], fallback_topics: list) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    def get_score(k, default=5):
        return clamp_score(raw.get(k, default))
    out = {}
    out["overall_score"] = get_score("overall_score", 5)
    out["technical_score"] = get_score("technical_score", out["overall_score"])
    out["communication_score"] = get_score("communication_score", out["overall_score"])
    out["problem_solving_score"] = get_score("problem_solving_score", out["overall_score"])
    strengths = raw.get("strengths") if isinstance(raw.get("strengths"), list) else []
    weaknesses = raw.get("weaknesses") if isinstance(raw.get("weaknesses"), list) else []
    out["strengths"] = [str(s)[:200] for s in strengths][:5]
    out["weaknesses"] = [str(s)[:200] for s in weaknesses][:5]
    if not out["strengths"]:
        out["strengths"] = ["Engaged in interview process"]
    if not out["weaknesses"]:
        out["weaknesses"] = ["Opportunities for deeper elaboration"]
    topics = raw.get("topics_covered") if isinstance(raw.get("topics_covered"), list) else fallback_topics
    out["topics_covered"] = [str(t)[:100] for t in (topics or fallback_topics)][:10]
    rec = str(raw.get("recommendation", "Moderate")).strip()
    # normalize
    rec_norm = rec.lower()
    if "strong" in rec_norm:
        rec = "Strong"
    elif "needs" in rec_norm:
        rec = "Needs Improvement"
    else:
        rec = "Moderate"
    out["recommendation"] = rec
    out["summary"] = str(raw.get("summary", "Candidate completed the interview."))[:600]
    out["detailed_feedback"] = str(raw.get("detailed_feedback", raw.get("summary", "No detailed feedback available.")))[:1000]
    return out
