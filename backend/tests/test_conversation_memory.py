import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Helpers for mocking LLM
def mock_chat_response(text="Mocked response"):
    return type("obj", (), {"response": text, "model": "qwen2.5:3b"})()

@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def clear_mem():
    from app.services import conversation_memory as cm
    from app.services.orchestrator import _last_intent
    cm.clear_all()
    _last_intent.clear()
    yield
    cm.clear_all()
    _last_intent.clear()

def test_new_conversation_returns_id(client):
    with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_chat_response("hello"))):
        resp = client.post("/api/chat", json={"message": "Hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert "conversation_id" in data and data["conversation_id"]
        assert "intent" in data
        assert "routing_reason" in data

def test_conversation_id_reuse_preserves_context(client):
    with patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock_chat_response("career reply"))):
        r1 = client.post("/api/chat", json={"message": "I want to become a Generative AI engineer."})
        assert r1.status_code == 200, r1.text
        cid = r1.json()["conversation_id"]
        # second message with same cid should reuse
        with patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock_chat_response("learning reply"))) as mock_gen:
            r2 = client.post("/api/chat", json={"message": "What should I learn first?", "conversation_id": cid})
            assert r2.status_code == 200, r2.text
            assert r2.json()["conversation_id"] == cid
            # Check that agent received context containing previous career message
            # mock_gen was called with prompt containing history
            assert mock_gen.called
            call_arg = mock_gen.call_args[0][0]  # first arg message
            assert "Generative AI" in call_arg or "Recent conversation" in call_arg

def test_separate_conversation_ids_isolated(client):
    with patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock_chat_response("reply"))), \
         patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_chat_response("reply"))):
        r1 = client.post("/api/chat", json={"message": "I want to become a data scientist.", "conversation_id": "conv-1"})
        assert r1.status_code == 200, r1.text
        r2 = client.post("/api/chat", json={"message": "Hello", "conversation_id": "conv-2"})
        assert r2.status_code == 200, r2.text
        assert r1.json()["conversation_id"] == "conv-1"
        assert r2.json()["conversation_id"] == "conv-2"
        from app.services import conversation_memory as cm
        assert len(cm.get_history("conv-1")) == 2  # user + assistant
        assert len(cm.get_history("conv-2")) == 2
        # histories should be different
        assert cm.get_history("conv-1")[0]["content"] != cm.get_history("conv-2")[0]["content"]

def test_memory_bounded_to_10_turns(client):
    from app.services import conversation_memory as cm
    # Send 12 turns (24 messages)
    with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_chat_response("reply"))):
        cid = "bounded-test"
        for i in range(12):
            client.post("/api/chat", json={"message": f"message {i}", "conversation_id": cid})
        hist = cm.get_history(cid)
        # Should be bounded to 20 messages (10 turns)
        assert len(hist) <= 20
        # Oldest should be dropped, newest retained
        assert hist[-1]["content"] == "reply" or "message 11" in hist[-2]["content"]

def test_contextual_followup_understands_previous(client):
    # First career
    with patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock_chat_response("career guidance..."))):
        r1 = client.post("/api/chat", json={"message": "I want to become a Generative AI engineer.", "conversation_id": "follow-1"})
        assert r1.status_code == 200, r1.text
        assert r1.json()["intent"] == "career"
        assert r1.json()["agent"] == "career"
    # Follow-up: "What should I learn first?" should be learning but with context
    with patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock_chat_response("learning roadmap for generative ai..."))) as mock_learning:
        r2 = client.post("/api/chat", json={"message": "What should I learn first?", "conversation_id": "follow-1"})
        assert r2.status_code == 200, r2.text
        # Should be learning intent (contains learn)
        assert r2.json()["intent"] == "learning"
        assert mock_learning.called
        prompt = mock_learning.call_args[0][0]
        assert "Generative AI" in prompt or "Recent conversation" in prompt

def test_specialized_agent_receives_context(client):
    with patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock_chat_response("roadmap"))) as mock_learn:
        r1 = client.post("/api/chat", json={"message": "I want to become a data scientist.", "conversation_id": "ctx-1"})
        # first is career, not learning, so not relevant
        # Now second message learning
        r2 = client.post("/api/chat", json={"message": "What skills do I need?", "conversation_id": "ctx-1"})
        # r2 should be learning and mock_learn should have been called with context containing data scientist
        assert mock_learn.called
        prompt = mock_learn.call_args[0][0]
        assert "data scientist" in prompt.lower() or "Recent conversation" in prompt

def test_general_intent_still_works(client):
    with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_chat_response("general reply"))):
        resp = client.post("/api/chat", json={"message": "Hello, how are you?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "general"
        assert data["agent"] is None
        assert "routing_reason" in data

def test_routing_metadata_returned(client):
    with patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock_chat_response("hi"))):
        resp = client.post("/api/chat", json={"message": "What should I learn for Generative AI?"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["intent"] == "learning"
        assert data["agent"] == "learning"
        assert "routing_reason" in data
        assert "skills" in data["routing_reason"].lower() or "learning" in data["routing_reason"].lower()

def test_backward_compatible_no_conversation_id(client):
    with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_chat_response("hi"))):
        resp = client.post("/api/chat", json={"message": "Hi there"})
        assert resp.status_code == 200
        assert "conversation_id" in resp.json()

def test_stream_includes_routing_and_conversation_id(client):
    async def mock_stream(*args, **kwargs):
        yield "hello "
        yield "world"

    with patch("app.services.orchestrator.generate_response_stream", new=mock_stream):
        resp = client.post("/api/chat/stream", json={"message": "Hello", "conversation_id": "stream-1"})
        assert resp.status_code == 200
        text = resp.text
        assert "meta" in text
        assert "stream-1" in text or "conversation_id" in text

def test_existing_orchestrator_detect_intent_still_works():
    from app.services.orchestrator import detect_intent
    assert detect_intent("What career should I choose?") == "career"
    assert detect_intent("Hello") == "general"
