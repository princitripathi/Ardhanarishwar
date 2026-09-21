"""Phase 3 routing tests: clear, ambiguous, context-dependent, multi-domain, general, follow-up."""
import pytest
from app.services.orchestrator import detect_intent, analyze_intents, score_intents, _detect_with_context, route_message
from app.services import conversation_memory as cm
from app.services.orchestrator import _last_intent
from unittest.mock import AsyncMock, patch

def mock_resp(text="mock"):
    return type("obj", (), {"response": text, "model": "qwen2.5:3b"})()

# ---- Clear intents ----
@pytest.mark.parametrize("msg,expected", [
    ("Help me plan my career growth", "career"),
    ("Improve my resume for FAANG", "resume"),
    ("Mock interview for backend engineer", "interview"),
    ("Create a roadmap to learn data science", "learning"),
    ("We need to hire Python developers and write a job description", "recruitment"),
    ("Workforce productivity and HR process help", "business"),
])
def test_clear_intents_still_routed(msg, expected):
    assert detect_intent(msg) == expected
    analysis = analyze_intents(msg)
    assert analysis["primary"] == expected
    assert analysis["is_multi_domain"] is False  # clear single

# ---- Ambiguous intents ----
@pytest.mark.parametrize("msg", [
    "Help",
    "I need help",
    "Advice?",
    "What should I do?",
    "I need help with my application",  # edge ambiguous
])
def test_ambiguous_queries_flagged_or_general(msg):
    analysis = analyze_intents(msg)
    # Ambiguous should be general or low confidence
    # For "I need help with my application" it's considered ambiguous general/resume but we mark ambiguous
    if msg == "I need help with my application":
        # This is the known edge: acceptable either, but we consider it ambiguous/general
        assert analysis["primary"] in ("general", "resume")
        # Our implementation marks this ambiguous when general
        if analysis["primary"] == "general":
            assert analysis["is_ambiguous"] is True or analysis["confidence"] == "low"
    else:
        assert analysis["primary"] == "general"
        # Very short should be ambiguous
        assert analysis["is_ambiguous"] is True or analysis["confidence"] == "low"

def test_ambiguous_does_not_break_clear():
    # Ensure "Help me plan my career growth" not marked ambiguous
    a = analyze_intents("Help me plan my career growth for the next 2 years")
    assert a["is_ambiguous"] is False
    assert a["confidence"] in ("high", "medium")

# ---- Multi-domain ----
def test_multi_domain_learning_interview():
    msg = "What skills should I learn for an AI Developer job and how should I prepare for the interview?"
    analysis = analyze_intents(msg)
    assert analysis["is_multi_domain"] is True
    assert "learning" in [analysis["primary"]] + analysis["secondary_intents"]
    assert "interview" in [analysis["primary"]] + analysis["secondary_intents"]
    # Primary should be learning (2 matches vs 1) or interview (priority) -> either but must have both
    assert set([analysis["primary"]] + analysis["secondary_intents"]) >= {"learning", "interview"}

def test_multi_domain_resume_interview():
    msg = "Help me improve my resume and prepare for the interview for a data scientist role"
    analysis = analyze_intents(msg)
    assert analysis["is_multi_domain"] is True
    assert "resume" in [analysis["primary"]] + analysis["secondary_intents"]
    assert "interview" in [analysis["primary"]] + analysis["secondary_intents"]

def test_multi_domain_recruitment_business():
    msg = "We need to hire someone and also improve workforce productivity and HR process"
    analysis = analyze_intents(msg)
    assert analysis["is_multi_domain"] is True
    assert "recruitment" in [analysis["primary"]] + analysis["secondary_intents"]
    assert "business" in [analysis["primary"]] + analysis["secondary_intents"]

def test_multi_domain_career_learning():
    msg = "Career advice and learning roadmap for becoming a data scientist"
    analysis = analyze_intents(msg)
    assert analysis["is_multi_domain"] is True
    assert "career" in [analysis["primary"]] + analysis["secondary_intents"]
    assert "learning" in [analysis["primary"]] + analysis["secondary_intents"]

def test_not_multi_for_single_domain():
    msg = "What career path suits someone with Python and communication skills?"
    analysis = analyze_intents(msg)
    # Career path special case should not be multi
    assert analysis["primary"] == "career"
    assert analysis["is_multi_domain"] is False

def test_score_intents_counts():
    scores = score_intents("What skills should I learn and interview prepare?")
    assert scores["learning"]["score"] >= 1
    assert scores["interview"]["score"] >= 1

# ---- Context-dependent ----
def test_context_dependent_followup_learning():
    cm.clear_all()
    _last_intent.clear()
    # Simulate prior career turn
    cid = "test-ctx-phase3-1"
    _last_intent[cid] = "career"
    history = [{"role": "user", "content": "I want to become a Generative AI Engineer"}, {"role": "assistant", "content": "Great career path"}]
    # Follow-up "What should I learn first?" should be learning via context special
    result = _detect_with_context("What should I learn first?", history, cid)
    assert result == "learning"

def test_context_dependent_followup_recruitment():
    _last_intent.clear()
    cid = "test-ctx-phase3-2"
    _last_intent[cid] = "recruitment"
    history = [{"role": "user", "content": "We need to hire Python developers"}, {"role": "assistant", "content": "oki"}]
    result = _detect_with_context("What about screening them?", history, cid)
    assert result == "recruitment"

def test_context_dependent_followup_interview():
    _last_intent.clear()
    cid = "test-ctx-phase3-3"
    _last_intent[cid] = "interview"
    history = [{"role": "user", "content": "Help me prepare for an AI/ML interview"}, {"role": "assistant", "content": "tips"}]
    result = _detect_with_context("Tell me more", history, cid)
    assert result == "interview"

def test_context_not_override_clear_intent():
    _last_intent.clear()
    cid = "test-ctx-phase3-4"
    _last_intent[cid] = "career"
    history = [{"role": "user", "content": "career advice"}, {"role": "assistant", "content": "done"}]
    # Clear interview intent should not be overridden by career last
    result = _detect_with_context("Give me Python interview questions", history, cid)
    assert result == "interview"

# ---- Unrelated / General ----
@pytest.mark.parametrize("msg", [
    "Hello, how are you?",
    "Tell me a joke",
    "What's the weather like today?",
    "Explain what Ardhanarishwar Solver does",
    "Thanks for your help!",
])
def test_general_unrelated(msg):
    assert detect_intent(msg) == "general"
    analysis = analyze_intents(msg)
    assert analysis["primary"] == "general"
    assert analysis["is_multi_domain"] is False

# ---- Follow-up questions (via route_message) ----
def test_followup_via_route_message():
    import asyncio
    cm.clear_all()
    _last_intent.clear()
    async def run():
        with patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock_resp("career reply"))):
            r1 = await route_message("I want to become a Generative AI Engineer", conversation_id="follow-phase3")
            assert r1["intent"] == "career"
            # Follow-up short should use context
            with patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock_resp("learning reply"))):
                r2 = await route_message("What should I learn first?", conversation_id="follow-phase3")
                assert r2["intent"] == "learning"
                assert r2["confidence"] is not None
    asyncio.run(run())

def test_multi_domain_route_message_metadata():
    import asyncio
    cm.clear_all()
    _last_intent.clear()
    # Mock any agent response; primary will be chosen via scoring
    mock = mock_resp("mock multi")
    async def run():
        with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock)), \
             patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock)), \
             patch("app.agents.interview_agent.generate_response", new=AsyncMock(return_value=mock)), \
             patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock)), \
             patch("app.agents.resume_agent.generate_response", new=AsyncMock(return_value=mock)), \
             patch("app.agents.recruitment_agent.generate_response", new=AsyncMock(return_value=mock)), \
             patch("app.agents.business_agent.generate_response", new=AsyncMock(return_value=mock)):
            msg = "What skills should I learn for an AI Developer job and how should I prepare for the interview?"
            res = await route_message(msg, conversation_id="multi-test-1")
            assert res["is_multi_domain"] is True
            assert len(res["secondary_intents"]) >= 1
            assert "interview" in [res["intent"]] + res["secondary_intents"]
            assert "learning" in [res["intent"]] + res["secondary_intents"]
            assert "confidence" in res
            assert "all_scores" in res
            assert "multi-domain" in res["routing_reason"].lower()
    asyncio.run(run())

def test_ambiguous_route_message_general():
    import asyncio
    cm.clear_all()
    _last_intent.clear()
    mock = mock_resp("general reply")
    async def run():
        with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock)):
            res = await route_message("Help me", conversation_id="amb-test")
            assert res["intent"] == "general"
            assert res["is_ambiguous"] is True or res["confidence"] == "low"
    asyncio.run(run())

# ---- Debuggable metadata ----
def test_routing_metadata_debuggable():
    analysis = analyze_intents("What skills should I learn and how should I prepare for the interview?")
    assert "all_scores" in analysis
    assert "matched_keywords" in analysis
    assert "confidence" in analysis
    assert "reason" in analysis
    # Check scores are understandable
    assert analysis["all_scores"]["learning"] >= 1
    assert analysis["all_scores"]["interview"] >= 1

def test_routing_priority_preserved():
    # Career path should still win over learning
    assert detect_intent("What career path suits someone with Python and communication skills?") == "career"
    # Certifications plural should still be learning
    assert detect_intent("Recommend certifications for cloud AI and MLOps") == "learning"
