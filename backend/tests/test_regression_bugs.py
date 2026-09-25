"""Regression tests for Bug 1 (stale intent after refresh) and Bug 2 related routing.

Covers:
A. AI/specialized question -> refresh (same cid) -> "hello" => general
B. AI question -> unrelated new question => new intent
C. AI question -> contextual follow-up => previous context retained
D. Greeting as first message => general
E. Refresh must not corrupt/reset routing logic
"""
import asyncio
from unittest.mock import AsyncMock, patch
from app.services.orchestrator import _detect_with_context, _last_intent, detect_intent, analyze_intents, route_message
from app.services import conversation_memory as cm

def mock_resp(text="mock"):
    return type("obj", (), {"response": text, "model": "qwen2.5:3b"})()

# ---- Helper for _detect_with_context directly ----

def test_bug1_greeting_after_specialized_intent_returns_general():
    """A. AI/specialized question -> refresh -> 'hello' => general, not stale intent."""
    cm.clear_all()
    _last_intent.clear()
    cid = "reg-b1-a"
    # Simulate prior specialized turn (career)
    _last_intent[cid] = "career"
    history = [{"role": "user", "content": "I want to become a Generative AI engineer"}, {"role": "assistant", "content": "Great"}]
    for greeting in ["Hello", "hello", "Hi", "hi", "Good morning", "good morning", "Hello!", "Hi there", "hey"]:
        result = _detect_with_context(greeting, history, cid)
        assert result == "general", f"Greeting '{greeting}' should remain general, got {result}"

def test_bug1_good_morning_variants():
    cm.clear_all()
    _last_intent.clear()
    cid = "reg-b1-a2"
    _last_intent[cid] = "learning"
    history = [{"role": "user", "content": "Create a roadmap to learn data science"}, {"role": "assistant", "content": "Roadmap"}]
    for g in ["Good morning", "Good afternoon", "Good evening"]:
        assert _detect_with_context(g, history, cid) == "general"

def test_bug1_unrelated_new_question_new_intent():
    """B. Previous career, new recruitment intent should win (explicit new intent)."""
    cm.clear_all()
    _last_intent.clear()
    cid = "reg-b1-b"
    _last_intent[cid] = "career"
    history = [{"role": "user", "content": "I want to become a data scientist"}, {"role": "assistant", "content": "Career..."}]
    # Unrelated explicit recruitment
    result = _detect_with_context("We need to hire Python developers and write a job description", history, cid)
    assert result == "recruitment"
    # Unrelated resume
    result2 = _detect_with_context("Help me improve my resume for FAANG", history, cid)
    assert result2 == "resume"
    # Unrelated interview
    result3 = _detect_with_context("Give me Python interview questions", history, cid)
    assert result3 == "interview"

def test_bug1_unrelated_general_question_stays_general():
    """B variant: previous specialized, new general unrelated should not inherit."""
    cm.clear_all()
    _last_intent.clear()
    cid = "reg-b1-b2"
    _last_intent[cid] = "career"
    history = [{"role": "user", "content": "I want to become a data scientist"}, {"role": "assistant", "content": "..."}]
    # "What is artificial intelligence?" is general and no cue -> should stay general
    result = _detect_with_context("What is artificial intelligence?", history, cid)
    assert result == "general"
    # Another general
    result2 = _detect_with_context("What is blockchain?", history, cid)
    assert result2 == "general"

def test_bug1_contextual_followup_retained():
    """C. Genuinely contextual follow-up should retain previous context."""
    cm.clear_all()
    _last_intent.clear()
    cid = "reg-b1-c"
    _last_intent[cid] = "career"
    history = [{"role": "user", "content": "I want to become a Generative AI Engineer"}, {"role": "assistant", "content": "Great career path"}]
    # "Explain it with an example" has pronoun cue -> should retain career
    result = _detect_with_context("Explain it with an example.", history, cid)
    assert result == "career"
    # "Can you explain it with a simple example?" -> retains
    result2 = _detect_with_context("Can you explain it with a simple example?", history, cid)
    assert result2 == "career"
    # Learning-specific follow-up after career maps to learning
    result3 = _detect_with_context("What should I learn first?", history, cid)
    assert result3 == "learning"
    # Recruitment follow-up
    _last_intent[cid] = "recruitment"
    history2 = [{"role": "user", "content": "We need to hire Python developers"}, {"role": "assistant", "content": "ok"}]
    result4 = _detect_with_context("What about screening them?", history2, cid)
    assert result4 == "recruitment"

def test_bug1_greeting_as_first_message():
    """D. Greeting as first message (no history) => general."""
    cm.clear_all()
    _last_intent.clear()
    assert detect_intent("Hello") == "general"
    assert detect_intent("Hi") == "general"
    assert detect_intent("Good morning") == "general"
    assert analyze_intents("Hello")["primary"] == "general"
    # Direct _detect_with_context with no history
    assert _detect_with_context("Hello", [], "new-cid") == "general"
    assert _detect_with_context("Hello", [], None) == "general"

def test_bug1_refresh_not_corrupt_routing():
    """E. Refresh (same cid) with greeting then new explicit intent should work sequence."""
    cm.clear_all()
    _last_intent.clear()
    cid = "reg-b1-e"
    # Step 1: career
    _last_intent[cid] = "career"
    history = [{"role": "user", "content": "I want to become a data scientist"}, {"role": "assistant", "content": "career advice"}]
    # Step 2: greeting after refresh -> should be general
    r1 = _detect_with_context("Hello", history, cid)
    assert r1 == "general"
    # Simulate that route_message would have set _last_intent to general after greeting
    _last_intent[cid] = r1  # general
    # Now history would include greeting; next message explicit learning should be learning
    history2 = history + [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there"}]
    r2 = _detect_with_context("What should I learn for Generative AI?", history2, cid)
    assert r2 == "learning"
    # Next follow-up should still work
    _last_intent[cid] = r2
    history3 = history2 + [{"role": "user", "content": "What should I learn for Generative AI?"}, {"role": "assistant", "content": "learning roadmap"}]
    r3 = _detect_with_context("Tell me more", history3, cid)
    assert r3 == "learning"

def test_bug1_route_message_integration_hello_after_career():
    """Integration via route_message: A. hello after career via same cid => general deterministic, no LLM."""
    cm.clear_all()
    _last_intent.clear()
    async def run():
        with patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock_resp("career reply"))):
            r1 = await route_message("I want to become a Generative AI engineer.", conversation_id="reg-int-a")
            assert r1["intent"] == "career"
            assert r1["conversation_id"] == "reg-int-a"
        # Refresh scenario: same cid, send hello – deterministic small-talk bypasses LLM
        with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_resp("SHOULD NOT BE CALLED"))) as mock_gen:
            r2 = await route_message("Hello", conversation_id="reg-int-a")
            assert r2["intent"] == "general", f"Expected general for hello after career, got {r2['intent']}"
            assert r2["response"] == "Hello! How can I help you today?"
            assert not mock_gen.called, "Deterministic hello should not call LLM"
            # Ensure response is concise and not career-injected
            assert "career" not in r2["response"].lower()
            assert "resume" not in r2["response"].lower()
    asyncio.run(run())

def test_bug1_route_message_integration_contextual_retained():
    """Integration C via route_message: contextual follow-up retains."""
    cm.clear_all()
    _last_intent.clear()
    async def run():
        with patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock_resp("career reply"))):
            r1 = await route_message("I want to become a Generative AI engineer.", conversation_id="reg-int-c")
            assert r1["intent"] == "career"
        # Now general but contextual follow-up: "What should I learn first?" should be learning but with context
        with patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock_resp("learning reply"))) as mock_learn:
            r2 = await route_message("What should I learn first?", conversation_id="reg-int-c")
            assert r2["intent"] == "learning"
            assert mock_learn.called
    asyncio.run(run())

def test_bug1_route_message_integration_greeting_first():
    """Integration D: greeting as first message – deterministic."""
    cm.clear_all()
    _last_intent.clear()
    async def run():
        with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_resp("SHOULD NOT BE CALLED"))) as mock_gen:
            r = await route_message("Hello", conversation_id="reg-int-d")
            assert r["intent"] == "general"
            assert r["agent"] is None
            assert r["response"] == "Hello! How can I help you today?"
            assert not mock_gen.called
            assert r["rag_used"] is False
    asyncio.run(run())


# ---- New deterministic small-talk tests for finalization bug ----

def test_deterministic_hello_fresh():
    cm.clear_all()
    _last_intent.clear()
    async def run():
        with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_resp("SHOULD NOT BE CALLED"))) as m:
            r = await route_message("hello", conversation_id="fresh-hello")
            assert r["intent"] == "general"
            assert r["response"] == "Hello! How can I help you today?"
            assert not m.called
            assert r["rag_used"] is False
            assert "career" not in r["response"].lower()
    asyncio.run(run())

def test_deterministic_no_fresh():
    cm.clear_all()
    _last_intent.clear()
    async def run():
        with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_resp("SHOULD NOT BE CALLED"))) as m:
            r = await route_message("no", conversation_id="fresh-no")
            assert r["intent"] == "general"
            assert r["response"] == "Okay. Let me know how I can help you."
            assert not m.called
            assert "career" not in r["response"].lower()
            assert "resume" not in r["response"].lower()
    asyncio.run(run())

def test_deterministic_thanks_okay_goodmorning():
    cm.clear_all()
    _last_intent.clear()
    async def run():
        cases = {
            "hi": "Hi! How can I help you today?",
            "thanks": "You're welcome! How can I help you today?",
            "okay": "Got it! How can I help you today?",
            "good morning": "Good morning! How can I help you today?",
        }
        for msg, expected in cases.items():
            with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_resp("SHOULD NOT BE CALLED"))) as m:
                r = await route_message(msg, conversation_id="fresh-"+msg)
                assert r["intent"] == "general", msg
                assert r["response"] == expected, msg
                assert not m.called, msg
    asyncio.run(run())

def test_deterministic_previous_career_no():
    """previous career topic + 'no' => general deterministic, no career injection."""
    cm.clear_all()
    _last_intent.clear()
    async def run():
        with patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock_resp("career reply"))):
            r1 = await route_message("I want to become a data scientist", conversation_id="cid-career-no")
            assert r1["intent"] == "career"
        with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_resp("SHOULD NOT BE CALLED"))) as m:
            r2 = await route_message("no", conversation_id="cid-career-no")
            assert r2["intent"] == "general"
            assert r2["response"] == "Okay. Let me know how I can help you."
            assert not m.called
            assert "career" not in r2["response"].lower()
    asyncio.run(run())

def test_deterministic_previous_ai_hello():
    """previous AI topic + hello => general deterministic."""
    cm.clear_all()
    _last_intent.clear()
    async def run():
        # Simulate prior general AI question (real would be general, but we test deterministic still)
        with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_resp("AI reply"))):
            r1 = await route_message("What is artificial intelligence?", conversation_id="cid-ai-hello")
            assert r1["intent"] == "general"
        with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_resp("SHOULD NOT BE CALLED"))) as m:
            r2 = await route_message("hello", conversation_id="cid-ai-hello")
            assert r2["intent"] == "general"
            assert r2["response"] == "Hello! How can I help you today?"
            assert not m.called
    asyncio.run(run())

def test_deterministic_latency_and_no_duplicate_llm():
    """Ensure deterministic hello is fast and does 0 LLM calls; contextual retains 1 call."""
    cm.clear_all()
    _last_intent.clear()
    import time as _time
    async def run():
        # Deterministic should be <200ms and 0 calls
        with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_resp("SHOULD NOT BE CALLED"))) as m:
            start = _time.perf_counter()
            r = await route_message("hello", conversation_id="fresh-latency")
            elapsed = (_time.perf_counter() - start) * 1000
            assert r["intent"] == "general"
            assert not m.called
            assert elapsed < 200, f"Deterministic hello too slow: {elapsed}ms"
        # Contextual should do 1 call
        with patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock_resp("career reply"))):
            await route_message("I want to become a Generative AI engineer", conversation_id="cid-lat-ctx")
        with patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock_resp("learning reply"))) as m2:
            r2 = await route_message("What should I learn first?", conversation_id="cid-lat-ctx")
            assert r2["intent"] == "learning"
            assert m2.call_count == 1, "Contextual should do exactly 1 LLM call"
        # Unrelated should also 1 call and correct intent
        with patch("app.agents.recruitment_agent.generate_response", new=AsyncMock(return_value=mock_resp("recruit")) ) as m3:
            r3 = await route_message("We need to hire Python developers", conversation_id="cid-lat-ctx")
            assert r3["intent"] == "recruitment"
            assert m3.call_count == 1
    asyncio.run(run())

def test_stream_deterministic_hello():
    """Stream path also deterministic – meta+single chunk, no Ollama stream."""
    cm.clear_all()
    _last_intent.clear()
    from app.services.orchestrator import stream_message
    async def run():
        with patch("app.services.orchestrator.generate_response_stream", new=AsyncMock()) as mock_stream:
            # mock_stream should NOT be called for deterministic
            events = []
            async for ev in stream_message("hello", conversation_id="stream-hello"):
                events.append(ev)
            assert events[0]["type"] == "meta"
            assert events[0]["intent"] == "general"
            assert events[1]["type"] == "chunk"
            assert events[1]["content"] == "Hello! How can I help you today?"
            assert not mock_stream.called
    asyncio.run(run())
