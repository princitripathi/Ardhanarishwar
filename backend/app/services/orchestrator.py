import logging
import re
from typing import Dict, Optional, List

from app.services.llm import generate_response, generate_response_stream
from app.services import conversation_memory as conv_mem

logger = logging.getLogger(__name__)

GENERAL_SYSTEM_PROMPT = """You are Ardhanarishwar AI Assistant.

Provide useful answers. Be clear and concise. Avoid pretending to have capabilities you do not have. Focus on career, education, professional development, recruitment, business and related assistance. Ask for clarification when the user's request is ambiguous."""

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


def detect_intent(message: str) -> str:
    msg = message.lower().strip()

    if _matches_recruitment(msg):
        return "recruitment"
    if _matches_resume(msg):
        return "resume"
    if _matches_interview(msg):
        return "interview"
    if _matches_learning(msg):
        return "learning"
    if _matches_career(msg):
        return "career"
    if _matches_business(msg):
        return "business"
    return "general"


def _detect_with_context(message: str, history: List[Dict[str, str]], conversation_id: Optional[str]) -> str:
    base = detect_intent(message)
    if base != "general":
        return base
    if not history or not conversation_id:
        return base
    last_intent = _last_intent.get(conversation_id)
    if not last_intent or last_intent == "general":
        return base
    lower = message.lower().strip()
    # follow-up cues
    followup_cues = ["what should", "what about", "how about", "tell me more", "which", "skills", "first", "next", "it ", "that ", "learn", "become", "roadmap", "course"]
    is_short = len(lower.split()) <= 9
    has_cue = any(cue in lower for cue in followup_cues)
    # If message is short or has cue, reuse last intent for contextual follow-up
    if is_short or has_cue:
        # Special mapping: if last was career and now asks about learning, prefer learning
        if last_intent == "career" and any(k in lower for k in ["learn", "skill", "course", "roadmap", "education"]):
            return "learning"
        return last_intent
    return base


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
        "study", "certification", "tutorial", "tutorials",
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


def _get_routing_reason(intent: str) -> str:
    return ROUTING_REASONS.get(intent, ROUTING_REASONS["general"])


async def route_message(message: str, conversation_id: Optional[str] = None) -> Dict[str, str]:
    # Handle conversation memory
    cid = conv_mem.get_conversation_id(conversation_id)
    history_before = conv_mem.get_history(cid)

    # Detect intent with context
    intent = _detect_with_context(message, history_before, cid)
    logger.info(f"Detected intent: {intent} (cid={cid})")

    # Add user message to memory (bounded)
    conv_mem.add_message(cid, "user", message)

    context = conv_mem.build_context(history_before)

    routing_reason = _get_routing_reason(intent)

    if intent == "general":
        # Pass context to LLM
        prompt = message
        if context:
            prompt = f"Recent conversation:\n{context}\n\nCurrent message: {message}"
        response = await generate_response(prompt, system_prompt=GENERAL_SYSTEM_PROMPT)
        result = {
            "response": response.response,
            "intent": intent,
            "agent": None,
            "routing_reason": routing_reason,
            "conversation_id": cid,
        }
        conv_mem.add_message(cid, "assistant", response.response)
        _last_intent[cid] = intent
        return result

    agent_fn = _load_agent(intent)
    if agent_fn is None:
        logger.error(f"No agent found for intent: {intent}")
        prompt = f"Recent conversation:\n{context}\n\nCurrent message: {message}" if context else message
        response = await generate_response(prompt, system_prompt=GENERAL_SYSTEM_PROMPT)
        result = {
            "response": response.response,
            "intent": intent,
            "agent": None,
            "routing_reason": routing_reason,
            "conversation_id": cid,
        }
        conv_mem.add_message(cid, "assistant", response.response)
        _last_intent[cid] = intent
        return result

    # Call specialized agent with context
    try:
        # Try with history param for new agents
        result = await agent_fn(message, context)
    except TypeError:
        # Fallback for agents without history support (mocked agents in tests)
        result = await agent_fn(message)

    # Ensure routing_reason and conversation_id present
    if isinstance(result, dict):
        result.setdefault("routing_reason", routing_reason)
        result.setdefault("conversation_id", cid)
        # Ensure intent/agent consistent
        result.setdefault("intent", intent)
        if result.get("agent") is None and intent != "general":
            result["agent"] = intent
        # Add to memory
        if result.get("response"):
            conv_mem.add_message(cid, "assistant", result["response"])
        _last_intent[cid] = intent
        return result
    # Fallback
    conv_mem.add_message(cid, "assistant", str(result))
    _last_intent[cid] = intent
    return {"response": str(result), "intent": intent, "agent": intent, "routing_reason": routing_reason, "conversation_id": cid}


async def stream_message(message: str, conversation_id: Optional[str] = None):
    cid = conv_mem.get_conversation_id(conversation_id)
    history_before = conv_mem.get_history(cid)
    intent = _detect_with_context(message, history_before, cid)
    logger.info(f"Detected intent (stream): {intent} (cid={cid})")
    context = conv_mem.build_context(history_before)
    system_prompt = _get_system_prompt_for_intent(intent)
    agent = None if intent == "general" else intent
    routing_reason = _get_routing_reason(intent)

    # Add user message
    conv_mem.add_message(cid, "user", message)
    _last_intent[cid] = intent

    # Yield metadata first so frontend can show intent immediately
    yield {"type": "meta", "intent": intent, "agent": agent, "routing_reason": routing_reason, "conversation_id": cid}
    # Build prompt with context
    prompt = f"Recent conversation:\n{context}\n\nCurrent message: {message}" if context else message
    full_response = []
    async for chunk in generate_response_stream(prompt, system_prompt=system_prompt):
        full_response.append(chunk)
        yield {"type": "chunk", "content": chunk}
    # After streaming complete, add assistant to memory
    if full_response:
        conv_mem.add_message(cid, "assistant", "".join(full_response))
