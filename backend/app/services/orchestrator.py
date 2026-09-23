import logging
import re
from typing import Dict, Optional, List, Tuple

from app.services.llm import generate_response, generate_response_stream, OllamaError
from app.services import conversation_memory as conv_mem

logger = logging.getLogger(__name__)

# Phase 4: lightweight RAG imports (no external AI APIs)
try:
    from app.rag.retrieval import retrieve as _rag_retrieve, format_context as _rag_format_context
    _RAG_AVAILABLE = True
except Exception as _e:
    logger.warning(f"RAG module not available: {_e}")
    _rag_retrieve = lambda *a, **k: []
    _rag_format_context = lambda *a, **k: ""
    _RAG_AVAILABLE = False

# Phase 5: controlled long-term user memory (separate from short-term conversation_memory)
try:
    from app.services import user_memory as _user_mem
    _MEMORY_AVAILABLE = True
except Exception as _e:
    logger.warning(f"User memory module not available: {_e}")
    _user_mem = None
    _MEMORY_AVAILABLE = False

# Phase 7: lightweight validation (no large model, low latency)
try:
    from app.services.validation import validate_chat_response, get_safe_fallback
    _VALIDATION_AVAILABLE = True
except Exception as _e:
    logger.warning(f"Validation module not available: {_e}")
    _VALIDATION_AVAILABLE = False
    validate_chat_response = lambda *a, **k: {"is_valid": True, "issues": [], "should_retry": False, "latency_ms": 0}
    get_safe_fallback = lambda *a, **k: "I apologize — I wasn't able to generate a complete response at the moment."

GENERAL_SYSTEM_PROMPT = """You are Ardhanarishwar Solver, the general assistant for the Ardhanarishwar Solver AI platform (local Qwen 2.5 3B via Ollama).

Responsibility: Help across career, education, professional development, recruitment, business and everyday general questions. Prioritize the user's actual request; answer what was asked, not a generic template.

Guidelines:
- Be actionable when helpful: use clear steps or bullets for multi-step tasks; for simple inputs (greetings, thanks, jokes) keep to 1-3 concise sentences.
- Match detail to complexity: simple → concise; complex → structured with headings/bullets.
- If the request is ambiguous or lacks needed detail, ask 1-2 specific clarifying questions instead of guessing.
- Never claim live browsing, live job listings, real-time market data, or access to proprietary/verified databases. If you lack verified data, say so and offer general best-practice guidance.
- Never invent ATS scores, interview banks, or course catalog entries.
- Tone: supportive, professional, concise."""

AGENTS = {
    "career": None,
    "resume": None,
    "interview": None,
    "learning": None,
    "recruitment": None,
    "business": None,
}

# Keep last intent per conversation for follow-up handling
_last_intent: Dict[str, str] = {}

ROUTING_REASONS = {
    "career": "The user is asking for career guidance",
    "resume": "The user is asking for resume help",
    "interview": "The user is asking for interview preparation",
    "learning": "The user is asking for skills and learning guidance",
    "recruitment": "The user is asking for hiring and recruitment help",
    "business": "The user is asking for business and workforce assistance",
    "general": "No specialized intent detected, using general assistant",
}

# Intent priority for tie-breaking (higher = earlier)
INTENT_PRIORITY = ["recruitment", "resume", "interview", "learning", "career", "business", "general"]


def _load_agent(name: str):
    if name == "career":
        from app.agents.career_agent import get_response
        return get_response
    elif name == "resume":
        from app.agents.resume_agent import get_response
        return get_response
    elif name == "interview":
        from app.agents.interview_agent import get_response
        return get_response
    elif name == "learning":
        from app.agents.learning_agent import get_response
        return get_response
    elif name == "recruitment":
        from app.agents.recruitment_agent import get_response
        return get_response
    elif name == "business":
        from app.agents.business_agent import get_response
        return get_response
    return None


def _word_match(msg, word):
    return bool(re.search(r'\b' + re.escape(word) + r'\b', msg))


def _matches_recruitment(msg: str) -> bool:
    recruitment_keywords = [
        "hire", "hiring", "recruit", "recruitment", "candidate", "screening",
        "job description", "job posting", "find candidates", "need to hire",
        "talent acquisition", "staffing", "headcount",
    ]
    for kw in recruitment_keywords:
        if _word_match(msg, kw):
            return True
    return False


def _matches_resume(msg: str) -> bool:
    resume_keywords = [
        "resume", "cv", "cover letter", "ats", "job application",
        "job applications", "resume builder", "cv structure",
    ]
    for kw in resume_keywords:
        if _word_match(msg, kw):
            return True
    return False


def _matches_interview(msg: str) -> bool:
    interview_keywords = [
        "interview", "mock interview", "behavioral", "technical interview",
        "interview preparation", "interview questions", "mock question",
    ]
    for kw in interview_keywords:
        if _word_match(msg, kw):
            return True
    return False


def _matches_learning(msg: str) -> bool:
    learning_keywords = [
        "learn", "learning", "skill", "skills", "education", "training",
        "roadmap", "course", "courses", "what should i learn", "what to learn",
        "study", "certification", "certifications", "tutorial", "tutorials",
    ]
    for kw in learning_keywords:
        if _word_match(msg, kw):
            return True
    # Handle plural / generic course mentions via substring for robustness
    if _word_match(msg, "courses"):
        return True
    return False


def _matches_career(msg: str) -> bool:
    career_keywords = [
        "career", "career path", "career planning", "job search", "job hunt",
        "apply for", "career decisions", "career change", "promotion",
        "advancement", "career development", "which career", "professional",
        "become a", "become an", "data scientist",
    ]
    for kw in career_keywords:
        if _word_match(msg, kw):
            return True
    # Fallback heuristic: "become" + professional context often indicates career intent
    if _word_match(msg, "become") and ("data" in msg or "scientist" in msg or "engineer" in msg or "developer" in msg):
        return True
    return False


def _matches_business(msg: str) -> bool:
    business_keywords = [
        "business", "company", "workforce", "hr", "human resource",
        "productivity", "employee", "organization", "process",
        "management", "corporate", "enterprise", "workplace",
        "profit", "revenue", "stakeholder",
    ]
    for kw in business_keywords:
        if _word_match(msg, kw):
            return True
    return False


# ---- Phase 3: lightweight scoring for debuggable routing ----

INTENT_KEYWORDS = {
    "recruitment": [
        "hire", "hiring", "recruit", "recruitment", "candidate", "screening",
        "job description", "job posting", "find candidates", "need to hire",
        "talent acquisition", "staffing", "headcount",
    ],
    "resume": [
        "resume", "cv", "cover letter", "ats", "job application",
        "job applications", "resume builder", "cv structure",
    ],
    "interview": [
        "interview", "mock interview", "behavioral", "technical interview",
        "interview preparation", "interview questions", "mock question",
    ],
    "learning": [
        "learn", "learning", "skill", "skills", "education", "training",
        "roadmap", "course", "courses", "what should i learn", "what to learn",
        "study", "certification", "certifications", "tutorial", "tutorials",
    ],
    "career": [
        "career", "career path", "career planning", "job search", "job hunt",
        "apply for", "career decisions", "career change", "promotion",
        "advancement", "career development", "which career", "professional",
        "become a", "become an", "data scientist",
    ],
    "business": [
        "business", "company", "workforce", "hr", "human resource",
        "productivity", "employee", "organization", "process",
        "management", "corporate", "enterprise", "workplace",
        "profit", "revenue", "stakeholder",
    ],
}


def _count_matches(msg: str, keywords: List[str]) -> Tuple[int, List[str]]:
    """Count how many keywords match (word-boundary) and return matched list."""
    matched = []
    for kw in keywords:
        if _word_match(msg, kw):
            matched.append(kw)
    return len(matched), matched


def score_intents(message: str) -> Dict[str, Dict]:
    """Score all intents for a message. Returns {intent: {score, matched}}."""
    msg = message.lower().strip()
    result = {}
    for intent, kws in INTENT_KEYWORDS.items():
        score, matched = _count_matches(msg, kws)
        result[intent] = {"score": score, "matched": matched}
    # general has no keywords; score stays 0
    return result


def analyze_intents(message: str) -> Dict:
    """Detailed intent analysis for debuggable routing.

    Returns:
      primary: top intent
      secondary_intents: list of other intents with score>=1 within 1 of primary or via 'and' connector
      all_scores: dict intent->score
      confidence: high/medium/low
      is_ambiguous: bool
      is_multi_domain: bool
    """
    msg = message.lower().strip()
    if not msg:
        return {
            "primary": "general",
            "secondary_intents": [],
            "all_scores": {k: 0 for k in INTENT_KEYWORDS},
            "confidence": "low",
            "is_ambiguous": True,
            "is_multi_domain": False,
            "reason": "Empty message",
        }

    # Preserve career path precedence (Phase 1 fix) — also reflected in scoring
    if "career path" in msg:
        scores = score_intents(message)
        # Force career to be primary in this case
        scores["career"]["score"] = max(scores["career"]["score"], 2)
        # Suppress learning secondary for this specific phrasing to avoid false multi
        if scores["learning"]["score"] == 1 and scores["career"]["score"] >= 2:
            scores["learning"]["score"] = 0
            scores["learning"]["matched"] = []
    else:
        scores = score_intents(message)

    # Extract scores
    all_scores = {k: v["score"] for k, v in scores.items()}
    # Sort by score desc, then priority
    sorted_intents = sorted(
        all_scores.keys(),
        key=lambda k: (all_scores[k], -INTENT_PRIORITY.index(k) if k in INTENT_PRIORITY else 99),
        reverse=True,
    )
    # Actually priority is lower index = higher priority, so we want earlier in priority to win ties.
    # Simpler: sort by (-score, priority_index)
    sorted_intents = sorted(
        all_scores.keys(),
        key=lambda k: (-all_scores[k], INTENT_PRIORITY.index(k) if k in INTENT_PRIORITY else 99),
    )
    primary = sorted_intents[0]
    max_score = all_scores[primary]
    second = sorted_intents[1] if len(sorted_intents) > 1 else None
    second_score = all_scores[second] if second else 0

    # If no keyword matched, primary is still top by priority but score 0 -> treat as general
    if max_score == 0:
        return {
            "primary": "general",
            "secondary_intents": [],
            "all_scores": all_scores,
            "matched_keywords": {k: scores[k]["matched"] for k in scores},
            "confidence": "low",
            "is_ambiguous": True if len(msg.split()) <= 4 else False,
            "is_multi_domain": False,
            "reason": "No keywords matched",
        }

    # Confidence
    if max_score >= 2 and (max_score - second_score) >= 2:
        confidence = "high"
    elif max_score >= 2 and (max_score - second_score) == 1:
        confidence = "medium"
    elif max_score >= 2 and max_score == second_score:
        confidence = "medium"
    elif max_score == 1 and second_score == 0:
        confidence = "low" if len(msg.split()) <= 8 else "medium"
    elif max_score == 1 and second_score == 1:
        confidence = "low"
    else:
        confidence = "medium"

    # Multi-domain detection: lightweight, debuggable
    # Criteria: at least 2 intents with score>=1, message contains connector "and"/","/"&"/"also",
    # and primary score >=1. Avoid false multi for career-path case already handled.
    distinct_matched = sum(1 for s in all_scores.values() if s >= 1)
    has_connector = any(c in msg for c in [" and ", ",", " & ", " also ", " plus ", " with "])
    # Count for secondary that would be considered
    secondary_candidates = [k for k in sorted_intents[1:] if all_scores[k] >= 1]
    # For short messages without connector, don't mark multi unless both scores >=2
    is_multi = False
    if distinct_matched >= 2:
        if has_connector and second_score >= 1:
            is_multi = True
        elif max_score >= 2 and second_score >= 2:
            is_multi = True
        elif max_score == 1 and second_score == 1 and len(msg.split()) >= 10:
            # Longer ambiguous with two equal single matches -> likely multi
            is_multi = True

    secondary_intents = []
    if is_multi:
        # Take up to 2 secondaries with score>=1, sorted by score/priority
        secondary_intents = [k for k in sorted_intents if k != primary and all_scores[k] >= 1][:2]

    # Ambiguous: low confidence, single weak match, short message, no connector
    is_ambiguous = False
    if confidence == "low" and max_score == 1 and not is_multi:
        # Very short or vague
        if len(msg.split()) <= 6 or msg in ["help", "help me", "i need help", "advice"]:
            is_ambiguous = True
        # Also if message like "I need help with my application" has only 1 weak match and is vague
        if distinct_matched == 1 and max_score == 1 and len(msg.split()) <= 8:
            # Check if it's the ambiguous edge case
            if "application" in msg and "help" in msg:
                is_ambiguous = True

    # Special: if ambiguous but also has career path, not ambiguous
    if "career path" in msg:
        is_ambiguous = False
        is_multi = False
        secondary_intents = []

    return {
        "primary": primary if max_score > 0 else "general",
        "secondary_intents": secondary_intents,
        "all_scores": all_scores,
        "matched_keywords": {k: scores[k]["matched"] for k in scores},
        "confidence": confidence,
        "is_ambiguous": is_ambiguous,
        "is_multi_domain": is_multi,
        "reason": f"scores {all_scores}, connector={has_connector}",
    }


def detect_intent(message: str) -> str:
    """Backward-compatible single intent detection, now score-based but same results for clear intents."""
    analysis = analyze_intents(message)
    return analysis["primary"]


def _detect_with_context(message: str, history: List[Dict[str, str]], conversation_id: Optional[str]) -> str:
    # First, run full analysis to get primary and multi/ambiguous info
    analysis = analyze_intents(message)
    base = analysis["primary"]

    # If base is already multi-domain, keep primary; context not needed to override
    # But we still want to handle follow-ups where base is general
    if base != "general":
        # If multi-domain, primary remains but we keep it; context doesn't override
        return base
    if not history or not conversation_id:
        return base
    last_intent = _last_intent.get(conversation_id)
    if not last_intent or last_intent == "general":
        return base
    lower = message.lower().strip()
    # follow-up cues (expanded for Phase 3)
    followup_cues = [
        "what should", "what about", "how about", "tell me more", "which", "skills", "first", "next",
        "it ", "that ", "learn", "become", "roadmap", "course", "prepare", "screening", "them"
    ]
    is_short = len(lower.split()) <= 9
    has_cue = any(cue in lower for cue in followup_cues)
    # If message is short or has cue, reuse last intent for contextual follow-up
    if is_short or has_cue:
        # Special mapping: if last was career and now asks about learning, prefer learning
        if last_intent == "career" and any(k in lower for k in ["learn", "skill", "course", "roadmap", "education"]):
            return "learning"
        # If last was recruitment and follow-up mentions screening, keep recruitment
        if last_intent == "recruitment" and any(k in lower for k in ["screen", "candidate", "them"]):
            return "recruitment"
        return last_intent
    return base


def _get_system_prompt_for_intent(intent: str) -> str:
    if intent == "general":
        return GENERAL_SYSTEM_PROMPT
    try:
        if intent == "career":
            from app.agents.career_agent import SYSTEM_PROMPT as P
            return P
        elif intent == "resume":
            from app.agents.resume_agent import SYSTEM_PROMPT as P
            return P
        elif intent == "interview":
            from app.agents.interview_agent import SYSTEM_PROMPT as P
            return P
        elif intent == "learning":
            from app.agents.learning_agent import SYSTEM_PROMPT as P
            return P
        elif intent == "recruitment":
            from app.agents.recruitment_agent import SYSTEM_PROMPT as P
            return P
        elif intent == "business":
            from app.agents.business_agent import SYSTEM_PROMPT as P
            return P
    except ImportError:
        pass
    return GENERAL_SYSTEM_PROMPT


def _get_routing_reason(intent: str, analysis: Optional[Dict] = None) -> str:
    base = ROUTING_REASONS.get(intent, ROUTING_REASONS["general"])
    if analysis is None:
        return base
    if analysis.get("is_multi_domain") and analysis.get("secondary_intents"):
        secondary = ", ".join(analysis["secondary_intents"])
        return f"{base} (multi-domain: also involves {secondary}; primary {intent} with confidence {analysis.get('confidence')})"
    if analysis.get("is_ambiguous"):
        return f"{base} (ambiguous query, low confidence {analysis.get('confidence')}; consider asking clarifying question)"
    if analysis.get("confidence") == "low" and intent != "general":
        return f"{base} (low confidence, scores {analysis.get('all_scores')})"
    return base


def _get_rag_results(message: str):
    """Phase 4: retrieve relevant chunks from local vector index.

    Returns (results, formatted_context, sources).
    Empty results means no relevant document (fallback).
    """
    if not _RAG_AVAILABLE:
        return [], "", []
    try:
        results = _rag_retrieve(message, top_k=3, threshold=0.12)
        ctx = _rag_format_context(results) if results else ""
        sources = [
            {
                "title": r["metadata"]["title"],
                "source": r["metadata"]["source"],
                "doc_id": r["metadata"]["doc_id"],
                "chunk_id": r["chunk_id"],
                "score": r["score"],
            }
            for r in results
        ]
        return results, ctx, sources
    except Exception as e:
        logger.warning(f"RAG retrieval error: {e}")
        return [], "", []


def _get_user_id(conversation_id: Optional[str], user_id: Optional[str]) -> str:
    """Resolve user_id for long-term memory.

    Priority: explicit user_id > conversation_id-derived (if looks like user) > default_user.
    For prototype without auth, default_user persists across conversations.
    """
    if user_id and isinstance(user_id, str) and user_id.strip():
        return user_id.strip()
    # For prototype, use default_user to share across conversations if no explicit id
    # Keep separation from short-term conversation_memory which is per conversation_id
    if _MEMORY_AVAILABLE and _user_mem:
        return _user_mem.DEFAULT_USER_ID
    return "default_user"

def _maybe_store_memory(user_id: str, message: str):
    if not _MEMORY_AVAILABLE or _user_mem is None:
        return None
    try:
        return _user_mem.maybe_update_from_message(user_id, message)
    except Exception as e:
        logger.warning(f"Memory store failed: {e}")
        return None

def _get_memory_context(user_id: str) -> str:
    if not _MEMORY_AVAILABLE or _user_mem is None:
        return ""
    try:
        return _user_mem.build_memory_context(user_id)
    except Exception as e:
        logger.warning(f"Memory context build failed: {e}")
        return ""

def _augment_with_rag(prompt_or_message: str, rag_context: str, has_results: bool) -> str:
    """Inject retrieved context or fallback note into prompt. Phase 8: keep concise to bound prompt tokens."""
    if has_results and rag_context:
        # rag_context already ends with citation instruction; keep supplemental instruction short
        return (
            f"{rag_context}\n\n"
            f"User question: {prompt_or_message}\n\n"
            "Instruction: Use retrieved docs when relevant; cite sources; distinguish retrieved vs general knowledge; don't fabricate company facts."
        )
    # No relevant docs: short guard note (system prompt already covers fabrication)
    # Avoid duplicate if already present
    if "[RAG note" in prompt_or_message:
        return prompt_or_message
    # Phase 8: keep concise but always include guard to preserve quality/test compatibility
    # Shortened from ~210 chars to ~115 chars saves ~24 tokens per request without losing instruction
    return (
        f"{prompt_or_message}\n\n"
        "[RAG note: No relevant documents found in approved local knowledge base; answer from general knowledge, don't fabricate company data.]"
    )

def _augment_with_memory(prompt: str, memory_context: str) -> str:
    if memory_context:
        return f"{memory_context}\n\n{prompt}"
    return prompt


def _sanitize_response(text: str) -> str:
    """Phase 2 safeguard: keep responses helpful and bounded.

    - Strip and ensure non-empty
    - Cap at 2000 chars to avoid excessive history bloat on next turn
    - Light hallucination softening: if response verbatim claims disallowed
      live access, append a brief correction note (prompt is primary defense).
    """
    if not text or not text.strip():
        return text
    cleaned = text.strip()
    # cap to avoid unbounded memory on next turn
    if len(cleaned) > 2000:
        cleaned = cleaned[:2000].rsplit(" ", 1)[0] + "…"
    lower = cleaned.lower()
    # soft safeguard: if obvious disallowed claim slipped through, add disclaimer
    # (do not heavily rewrite – prompt is the main guard)
    hallucination_markers = [
        "i have access to live job listings",
        "i browsed the internet",
        "your ats score is",
    ]
    if any(p in lower for p in hallucination_markers):
        logger.warning("Hallucination marker detected in response; adding disclaimer")
        # Append concise disclaimer instead of attempting risky rewrite
        if "general guidance" not in lower:
            cleaned += "\n\nNote: This is general guidance based on best practices, not verified live data."
    return cleaned


async def _validated_generate(prompt: str, system_prompt: Optional[str], intent: Optional[str], rag_used: bool, rag_results: Optional[List[Dict]], message: Optional[str], max_retries: int = 1) -> Tuple[str, Dict]:
    """Phase 7: call LLM with lightweight validation and bounded retry."""
    attempt = 0
    last_validation = {"is_valid": True, "issues": [], "should_retry": False, "latency_ms": 0}
    while attempt <= max_retries:
        try:
            raw = await generate_response(prompt, system_prompt=system_prompt)
        except OllamaError as e:
            logger.warning(f"LLM unavailable during _validated_generate: {e.message}")
            fallback = get_safe_fallback(intent=intent, rag_used=rag_used)
            if rag_used:
                fallback += " (Based on retrieved context where available; general guidance otherwise.)"
            return fallback, {"is_valid": True, "issues": [f"llm_unavailable:{e.message}"], "should_retry": False, "latency_ms": 0}
        except Exception as e:
            logger.warning(f"LLM unexpected error during _validated_generate: {e}")
            fallback = get_safe_fallback(intent=intent, rag_used=rag_used)
            return fallback, {"is_valid": True, "issues": ["llm_error"], "should_retry": False, "latency_ms": 0}
        text = raw.response if hasattr(raw, "response") else str(raw)
        if _VALIDATION_AVAILABLE:
            validation = validate_chat_response(text, intent=intent, rag_used=rag_used, rag_results=rag_results, message=message)
            last_validation = validation
            if validation["is_valid"]:
                return text, validation
            # Invalid
            logger.warning(f"Validation failed (attempt {attempt}): {validation['issues']} for intent={intent} rag_used={rag_used}")
            if validation["should_retry"] and attempt < max_retries:
                attempt += 1
                # Bounded retry: add instruction to avoid previous artifact
                prompt = prompt + "\n\n[Validation note: previous response was malformed/empty, please provide a concise well-formed answer without repetition or error artifacts.]"
                continue
            else:
                # Safe fallback (preserve good intent, no hallucination)
                fallback = get_safe_fallback(intent=intent, rag_used=rag_used)
                # For RAG, ensure fallback distinguishes retrieved vs generated
                if rag_used:
                    fallback += " (Based on retrieved context where available; general guidance otherwise.)"
                return fallback, validation
        else:
            return text, last_validation
    # Should not reach here
    fallback = get_safe_fallback(intent=intent, rag_used=rag_used)
    return fallback, last_validation


def _validated_agent_response(text: str, intent: Optional[str], rag_used: bool, rag_results: Optional[List[Dict]], message: Optional[str]) -> Tuple[str, Dict]:
    """Validate agent response without LLM retry (agent already called). Returns validated text or fallback."""
    if not _VALIDATION_AVAILABLE:
        return text, {"is_valid": True, "issues": [], "should_retry": False, "latency_ms": 0}
    validation = validate_chat_response(text, intent=intent, rag_used=rag_used, rag_results=rag_results, message=message)
    if validation["is_valid"]:
        return text, validation
    logger.warning(f"Agent validation failed: {validation['issues']} for intent={intent}")
    if validation["should_retry"]:
        # For agent, retry would require re-calling agent — handled by caller
        return text, validation  # caller decides to retry
    fallback = get_safe_fallback(intent=intent, rag_used=rag_used)
    return fallback, validation


async def route_message(message: str, conversation_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, str]:
    # Resolve long-term user memory id (separate from short-term conversation_id)
    uid = _get_user_id(conversation_id, user_id)
    # Phase 5: controlled long-term memory extraction (only explicit useful info)
    _maybe_store_memory(uid, message)

    # Handle conversation memory (short-term, per conversation)
    cid = conv_mem.get_conversation_id(conversation_id)
    history_before = conv_mem.get_history(cid)

    # Phase 3: full analysis
    analysis = analyze_intents(message)
    # Context check: may override general to last_intent
    context_intent = _detect_with_context(message, history_before, cid)
    # If context suggests different from analysis primary and analysis was general/ambiguous, use context
    if context_intent != analysis["primary"] and analysis["primary"] == "general":
        # Re-analyze to reflect context choice but keep original analysis for metadata
        intent = context_intent
        # Update analysis to reflect context override for routing reason
        analysis["primary"] = intent
        analysis["reason"] += f" + context override to {intent}"
        logger.info(f"Context override: {analysis} (cid={cid})")
    else:
        intent = analysis["primary"]
        # Also consider _detect_with_context result when analysis primary is general but context says otherwise
        # Already handled above; otherwise keep analysis primary

    logger.info(f"Detected intent: {intent} (analysis={analysis}, cid={cid})")

    # Add user message to memory (bounded)
    conv_mem.add_message(cid, "user", message)

    context = conv_mem.build_context(history_before)

    routing_reason = _get_routing_reason(intent, analysis)

    # Phase 4: RAG retrieval (lightweight local)
    rag_results, rag_context, rag_sources = _get_rag_results(message)
    rag_used = len(rag_results) > 0
    logger.info(f"RAG retrieval: used={rag_used} count={len(rag_results)} (cid={cid})")

    # Phase 5: long-term memory context (structured, bounded)
    memory_context = _get_memory_context(uid)

    if intent == "general":
        # Bounded, relevant context only — avoid dominating old history
        prompt = message
        if context:
            prompt = f"Recent conversation (use only if relevant to current message; do not repeat verbatim unless asked):\n{context}\n\nCurrent message: {message}"
        # Inject long-term memory (separate from short-term)
        prompt = _augment_with_memory(prompt, memory_context)
        # Inject RAG context (or fallback note) before LLM call
        prompt = _augment_with_rag(prompt, rag_context, rag_used)
        # Phase 7: validated generation with bounded retry
        validated_text, validation = await _validated_generate(prompt, GENERAL_SYSTEM_PROMPT, intent, rag_used, rag_results, message)
        sanitized = _sanitize_response(validated_text)
        result = {
            "response": sanitized,
            "intent": intent,
            "agent": None,
            "routing_reason": routing_reason,
            "conversation_id": cid,
            "confidence": analysis.get("confidence"),
            "is_ambiguous": analysis.get("is_ambiguous"),
            "is_multi_domain": analysis.get("is_multi_domain"),
            "secondary_intents": analysis.get("secondary_intents", []),
            "all_scores": analysis.get("all_scores"),
            "rag_used": rag_used,
            "rag_sources": rag_sources,
            "rag_count": len(rag_results),
            "validation_issues": validation.get("issues", []),
            "validation_passed": validation.get("is_valid", True),
            "validation_latency_ms": validation.get("latency_ms", 0),
        }
        conv_mem.add_message(cid, "assistant", sanitized)
        _last_intent[cid] = intent
        return result

    agent_fn = _load_agent(intent)
    if agent_fn is None:
        logger.error(f"No agent found for intent: {intent}")
        # Keep prompt style consistent with context guidance
        if context:
            prompt = f"Recent conversation (use only if relevant to current message; do not repeat verbatim unless asked):\n{context}\n\nCurrent message: {message}"
        else:
            prompt = message
        # Inject memory then RAG
        prompt = _augment_with_memory(prompt, memory_context)
        prompt = _augment_with_rag(prompt, rag_context, rag_used)
        validated_text, validation = await _validated_generate(prompt, GENERAL_SYSTEM_PROMPT, intent, rag_used, rag_results, message)
        sanitized = _sanitize_response(validated_text)
        result = {
            "response": sanitized,
            "intent": intent,
            "agent": None,
            "routing_reason": routing_reason,
            "conversation_id": cid,
            "confidence": analysis.get("confidence"),
            "is_ambiguous": analysis.get("is_ambiguous"),
            "is_multi_domain": analysis.get("is_multi_domain"),
            "secondary_intents": analysis.get("secondary_intents", []),
            "all_scores": analysis.get("all_scores"),
            "rag_used": rag_used,
            "rag_sources": rag_sources,
            "rag_count": len(rag_results),
            "validation_issues": validation.get("issues", []),
            "validation_passed": validation.get("is_valid", True),
            "validation_latency_ms": validation.get("latency_ms", 0),
        }
        conv_mem.add_message(cid, "assistant", sanitized)
        _last_intent[cid] = intent
        return result

    # For multi-domain, augment prompt to acknowledge secondary
    effective_context = context
    augmented_message = message
    if analysis.get("is_multi_domain") and analysis.get("secondary_intents"):
        secondary = ", ".join(analysis["secondary_intents"])
        augmented_message = f"{message}\n\n[Routing note: This is a multi-domain query. Primary: {intent}, also involves: {secondary}. Address both aspects, prioritizing {intent} but Briefly covering {secondary} or suggesting next step.]"
    # Phase 4: inject RAG into augmented_message (preserve multi-domain note)
    if rag_used and rag_context:
        augmented_message = f"{rag_context}\n\nUser question: {augmented_message}\n\nInstruction: Ground answer in retrieved docs when relevant. Distinguish retrieved info vs general knowledge."
    elif not rag_used:
        # Add fallback note for no relevant docs (so agent prompt instructs not to fabricate) - concise Phase 8
        augmented_message = f"{augmented_message}\n\n[RAG note: No relevant documents found in approved local knowledge base; answer from general knowledge, don't fabricate company data.]"
    # Phase 5: inject long-term memory into augmented_message
    if memory_context:
        augmented_message = f"{memory_context}\n\nUser question: {augmented_message}"

    # Call specialized agent with context (use augmented message for multi-domain) — with Phase 7 validation and bounded retry
    attempt = 0
    max_agent_retries = 1
    last_validation = {"is_valid": True, "issues": [], "should_retry": False, "latency_ms": 0}
    while True:
        try:
            result = await agent_fn(augmented_message, effective_context)
        except OllamaError as e:
            logger.warning(f"Agent LLM unavailable for intent {intent}: {e.message}")
            fallback_text = get_safe_fallback(intent=intent, rag_used=rag_used)
            result = {"response": fallback_text, "intent": intent, "agent": intent}
            last_validation = {"is_valid": True, "issues": [f"llm_unavailable:{e.message}"], "should_retry": False, "latency_ms": 0}
            break
        except TypeError:
            try:
                result = await agent_fn(augmented_message)
            except OllamaError as e2:
                logger.warning(f"Agent LLM unavailable (fallback call) for intent {intent}: {e2.message}")
                fallback_text = get_safe_fallback(intent=intent, rag_used=rag_used)
                result = {"response": fallback_text, "intent": intent, "agent": intent}
                last_validation = {"is_valid": True, "issues": [f"llm_unavailable:{e2.message}"], "should_retry": False, "latency_ms": 0}
                break
        except Exception as e:
            logger.warning(f"Agent unexpected error for intent {intent}: {e}")
            fallback_text = get_safe_fallback(intent=intent, rag_used=rag_used)
            result = {"response": fallback_text, "intent": intent, "agent": intent}
            last_validation = {"is_valid": True, "issues": ["agent_error"], "should_retry": False, "latency_ms": 0}
            break

        # Extract response text for validation
        resp_text = result.get("response") if isinstance(result, dict) else str(result)
        if _VALIDATION_AVAILABLE:
            validation = validate_chat_response(resp_text, intent=intent, rag_used=rag_used, rag_results=rag_results, message=message)
            last_validation = validation
            if validation["is_valid"]:
                break
            logger.warning(f"Agent validation failed (attempt {attempt}): {validation['issues']}")
            if validation["should_retry"] and attempt < max_agent_retries:
                attempt += 1
                # Add hint to prompt for retry
                augmented_message = augmented_message + "\n\n[Validation note: previous response was malformed/empty, please provide a concise well-formed answer without repetition or error artifacts.]"
                continue
            else:
                # Safe fallback for agent
                fallback_text = get_safe_fallback(intent=intent, rag_used=rag_used)
                if isinstance(result, dict):
                    result["response"] = fallback_text
                else:
                    result = {"response": fallback_text, "intent": intent, "agent": intent}
                break
        else:
            break

    # Ensure routing_reason and conversation_id present
    if isinstance(result, dict):
        result.setdefault("routing_reason", routing_reason)
        result.setdefault("conversation_id", cid)
        # Ensure intent/agent consistent
        result.setdefault("intent", intent)
        if result.get("agent") is None and intent != "general":
            result["agent"] = intent
        # Add Phase 3 metadata
        result.setdefault("confidence", analysis.get("confidence"))
        result.setdefault("is_ambiguous", analysis.get("is_ambiguous"))
        result.setdefault("is_multi_domain", analysis.get("is_multi_domain"))
        result.setdefault("secondary_intents", analysis.get("secondary_intents", []))
        result.setdefault("all_scores", analysis.get("all_scores"))
        # Phase 4: RAG metadata
        result.setdefault("rag_used", rag_used)
        result.setdefault("rag_sources", rag_sources)
        result.setdefault("rag_count", len(rag_results))
        # Phase 7: validation metadata
        result.setdefault("validation_issues", last_validation.get("issues", []))
        result.setdefault("validation_passed", last_validation.get("is_valid", True))
        result.setdefault("validation_latency_ms", last_validation.get("latency_ms", 0))
        # Safeguard: sanitize agent response before memory/store
        if result.get("response"):
            result["response"] = _sanitize_response(result["response"])
            conv_mem.add_message(cid, "assistant", result["response"])
        _last_intent[cid] = intent
        return result
    # Fallback
    sanitized_fallback = _sanitize_response(str(result))
    conv_mem.add_message(cid, "assistant", sanitized_fallback)
    _last_intent[cid] = intent
    return {"response": sanitized_fallback, "intent": intent, "agent": intent, "routing_reason": routing_reason, "conversation_id": cid,
            "confidence": analysis.get("confidence"), "is_ambiguous": analysis.get("is_ambiguous"), "is_multi_domain": analysis.get("is_multi_domain"),
            "secondary_intents": analysis.get("secondary_intents", []), "all_scores": analysis.get("all_scores"),
            "rag_used": rag_used, "rag_sources": rag_sources, "rag_count": len(rag_results),
            "validation_issues": last_validation.get("issues", []), "validation_passed": last_validation.get("is_valid", True), "validation_latency_ms": last_validation.get("latency_ms", 0)}


async def stream_message(message: str, conversation_id: Optional[str] = None, user_id: Optional[str] = None):
    uid = _get_user_id(conversation_id, user_id)
    _maybe_store_memory(uid, message)
    cid = conv_mem.get_conversation_id(conversation_id)
    history_before = conv_mem.get_history(cid)
    # Phase 3: use analysis for streaming as well
    analysis = analyze_intents(message)
    context_intent = _detect_with_context(message, history_before, cid)
    if context_intent != analysis["primary"] and analysis["primary"] == "general":
        intent = context_intent
        analysis["primary"] = intent
    else:
        intent = analysis["primary"]
    logger.info(f"Detected intent (stream): {intent} (analysis={analysis}, cid={cid})")
    context = conv_mem.build_context(history_before)
    system_prompt = _get_system_prompt_for_intent(intent)
    agent = None if intent == "general" else intent
    routing_reason = _get_routing_reason(intent, analysis)

    # Phase 4: RAG for streaming
    rag_results, rag_context, rag_sources = _get_rag_results(message)
    rag_used = len(rag_results) > 0
    # Phase 5: memory for streaming
    memory_context = _get_memory_context(uid)

    # Add user message
    conv_mem.add_message(cid, "user", message)
    _last_intent[cid] = intent

    # Yield metadata first so frontend can show intent immediately (include RAG info)
    yield {"type": "meta", "intent": intent, "agent": agent, "routing_reason": routing_reason, "conversation_id": cid,
           "confidence": analysis.get("confidence"), "is_ambiguous": analysis.get("is_ambiguous"),
           "is_multi_domain": analysis.get("is_multi_domain"), "secondary_intents": analysis.get("secondary_intents", []),
           "rag_used": rag_used, "rag_sources": rag_sources, "rag_count": len(rag_results)}
    # Bounded, relevant context only
    if context:
        prompt = f"Recent conversation (use only if relevant to current message; do not repeat verbatim unless asked):\n{context}\n\nCurrent message: {message}"
    else:
        prompt = message
    # Phase 5: memory
    prompt = _augment_with_memory(prompt, memory_context)
    # Phase 4: inject RAG into streaming prompt
    prompt = _augment_with_rag(prompt, rag_context, rag_used)
    # For multi-domain streaming, we could augment prompt similarly, but keep simple for streaming
    if analysis.get("is_multi_domain") and analysis.get("secondary_intents"):
        secondary = ", ".join(analysis["secondary_intents"])
        prompt = f"{prompt}\n\n[Multi-domain: primary {intent}, also {secondary}]"
    full_response = []
    try:
        async for chunk in generate_response_stream(prompt, system_prompt=system_prompt):
            full_response.append(chunk)
            yield {"type": "chunk", "content": chunk}
    except OllamaError as e:
        logger.warning(f"Stream LLM unavailable: {e.message}")
        fallback = get_safe_fallback(intent=intent, rag_used=rag_used)
        # Yield fallback as single chunk so frontend receives usable content instead of error only
        yield {"type": "chunk", "content": fallback}
        full_response = [fallback]
    except Exception as e:
        logger.warning(f"Stream unexpected error: {e}")
        fallback = get_safe_fallback(intent=intent, rag_used=rag_used)
        yield {"type": "chunk", "content": fallback}
        full_response = [fallback]
    # After streaming complete, validate and add assistant to memory (sanitized, capped) — Phase 7
    if full_response:
        raw_final = "".join(full_response)
        if _VALIDATION_AVAILABLE:
            v = validate_chat_response(raw_final, intent=intent, rag_used=rag_used, rag_results=rag_results, message=message)
            if not v["is_valid"]:
                logger.warning(f"Stream validation failed: {v['issues']}")
                if not v["should_retry"]:
                    raw_final = get_safe_fallback(intent=intent, rag_used=rag_used)
                # For should_retry, we already streamed invalid content; keep fallback for history only to avoid duplicate stream
                # Do not re-stream fallback to keep latency bounded
        final_text = _sanitize_response(raw_final)
        conv_mem.add_message(cid, "assistant", final_text)

