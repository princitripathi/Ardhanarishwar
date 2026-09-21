"""Phase 5 controlled long-term user memory tests.

Covers:
- creating memory
- updating memory
- retrieving memory
- irrelevant information not being stored
- using memory in prompts
- clearing memory
- persistence across restart (SQLite file)
- bounded / structured / editable / sensitive filtering
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.services import user_memory as mem
from app.services import conversation_memory as cm
from app.services.orchestrator import _last_intent


@pytest.fixture(autouse=True)
def clean_memory():
    mem.clear_all()
    cm.clear_all()
    _last_intent.clear()
    # Also clear RAG to avoid cross-test pollution
    try:
        from app.rag.ingestion import clear_documents
        from app.rag.store import reset_store
        clear_documents()
        reset_store()
    except Exception:
        pass
    yield
    mem.clear_all()
    cm.clear_all()
    _last_intent.clear()
    try:
        from app.rag.ingestion import clear_documents
        from app.rag.store import reset_store
        clear_documents()
        reset_store()
    except Exception:
        pass

def mock_resp(text="Mocked response"):
    return type("obj", (), {"response": text, "model": "qwen2.5:3b"})()

# ---- Creating memory ----
def test_create_memory_explicit():
    upd = mem.extract_memory_updates("I want to become a Generative AI Developer.")
    assert "career_goal" in upd
    profile = mem.upsert_profile("user_create", upd)
    assert profile["career_goal"] == "Generative AI Developer"
    assert profile["target_role"] == "Generative AI Developer"
    fetched = mem.get_profile("user_create")
    assert fetched["career_goal"] == "Generative AI Developer"

def test_create_memory_preferred_name():
    upd = mem.extract_memory_updates("My name is Priya")
    assert upd.get("preferred_name") == "Priya"
    profile = mem.upsert_profile("u_name", upd)
    assert profile["preferred_name"] == "Priya"

def test_create_memory_skills():
    upd = mem.extract_memory_updates("I know Python, Java and Machine Learning")
    assert "known_skills" in upd
    assert "Python" in upd["known_skills"]
    profile = mem.upsert_profile("u_skills", upd)
    assert "Python" in profile["known_skills"]

def test_create_memory_learning_interests():
    upd = mem.extract_memory_updates("I want to learn MLOps and Generative AI")
    assert "learning_interests" in upd
    profile = mem.upsert_profile("u_learn", upd)
    assert "MLOps" in profile["learning_interests"]

# ---- Updating memory ----
def test_update_memory_career_goal():
    mem.upsert_profile("u_upd", {"career_goal": "Data Scientist"})
    assert mem.get_profile("u_upd")["career_goal"] == "Data Scientist"
    mem.upsert_profile("u_upd", {"career_goal": "Generative AI Developer"})
    assert mem.get_profile("u_upd")["career_goal"] == "Generative AI Developer"
    # Ensure target_role also updates? Our extract sets both, but direct upsert may keep old if not specified
    # Here we set only career_goal, target_role remains old? Our merge keeps old if not updating
    # Explicitly update target_role as well
    mem.upsert_profile("u_upd", {"target_role": "ML Engineer"})
    assert mem.get_profile("u_upd")["target_role"] == "ML Engineer"

def test_update_memory_skills_merge():
    mem.upsert_profile("u_merge", {"known_skills": ["Python"]})
    mem.upsert_profile("u_merge", {"known_skills": ["Java"]})
    profile = mem.get_profile("u_merge")
    assert "Python" in profile["known_skills"]
    assert "Java" in profile["known_skills"]
    # Bounded: add many, ensure max 10
    mem.upsert_profile("u_merge", {"known_skills": [f"Skill{i}" for i in range(20)]})
    assert len(mem.get_profile("u_merge")["known_skills"]) <= 10

# ---- Retrieving memory ----
def test_retrieve_memory_exists():
    mem.upsert_profile("u_ret", {"career_goal": "AI Engineer", "preferred_name": "Amit"})
    p = mem.get_profile("u_ret")
    assert p["user_id"] == "u_ret"
    assert p["career_goal"] == "AI Engineer"
    assert p["preferred_name"] == "Amit"
    # List
    all_profiles = mem.list_profiles()
    assert any(x["user_id"] == "u_ret" for x in all_profiles)

def test_retrieve_memory_nonexistent():
    assert mem.get_profile("no_such_user_xyz") is None

# ---- Irrelevant information not being stored ----
def test_irrelevant_not_stored():
    assert mem.extract_memory_updates("What should I learn next?") == {}
    assert mem.extract_memory_updates("What's the weather like?") == {}
    assert mem.extract_memory_updates("Tell me a joke") == {}
    assert mem.extract_memory_updates("Hello, how are you?") == {}

    # Via orchestrator - should not create profile
    import asyncio
    async def run():
        from app.services.orchestrator import route_message
        # Patch at llm level to cover both general and agent paths (Phase 9: robust mocking)
        with patch("app.services.llm.generate_response", new=AsyncMock(return_value=mock_resp("hi"))), \
             patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_resp("hi"))), \
             patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock_resp("hi"))), \
             patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock_resp("hi"))):
            await route_message("What should I learn next?", conversation_id="c_irr", user_id="user_irr")
        # Check no profile or empty
        p = mem.get_profile("user_irr")
        # Either None or empty fields
        if p:
            assert not p.get("career_goal")
            assert not p.get("preferred_name")
    asyncio.run(run())

def test_sensitive_not_stored():
    assert mem.extract_memory_updates("my password is supersecret123") == {}
    assert mem.extract_memory_updates("my api key is abc123") == {}
    assert mem.extract_memory_updates("credit card 4111 1111 1111 1111") == {}
    # Even via upsert, sensitive should be filtered
    mem.upsert_profile("u_sens", {"preferred_name": "my password is 123"})
    # Our upsert filters sensitive? It checks contains_sensitive_info and should skip
    # But preferred_name containing password should be blocked
    p = mem.get_profile("u_sens")
    # If filtered, preferred_name should be None or not containing password
    if p and p.get("preferred_name"):
        assert "password" not in p["preferred_name"].lower()

# ---- Using memory in prompts ----
def test_using_memory_in_prompts():
    import asyncio
    mem.upsert_profile("user_prompt", {"career_goal": "Generative AI Developer", "known_skills": ["Python"]})

    async def run():
        from app.services.orchestrator import route_message
        with patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock_resp("learning reply"))) as mock_learn:
            await route_message("What should I learn next?", conversation_id="c_prompt", user_id="user_prompt")
            assert mock_learn.called
            prompt = mock_learn.call_args[0][0]
            # Memory should be injected
            assert "Generative AI Developer" in prompt
            assert "User Profile" in prompt
    asyncio.run(run())

def test_using_memory_across_conversations_example():
    import asyncio
    async def run():
        from app.services.orchestrator import route_message
        # First conversation: set goal
        with patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock_resp("career reply"))):
            await route_message("I want to become a Generative AI Developer.", conversation_id="convA", user_id="cross_user")
        # Verify stored
        assert mem.get_profile("cross_user")["career_goal"] == "Generative AI Developer"
        # Second conversation different id, same user
        with patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock_resp("learning reply"))) as mock:
            await route_message("What should I learn next?", conversation_id="convB", user_id="cross_user")
            assert mock.called
            prompt = mock.call_args[0][0]
            assert "Generative AI Developer" in prompt
    asyncio.run(run())

def test_memory_separated_from_short_term():
    import asyncio
    mem.upsert_profile("sep_user", {"career_goal": "Data Scientist"})
    async def run():
        from app.services.orchestrator import route_message
        # Short term conversation
        with patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock_resp("r1"))):
            await route_message("I want to become a Data Scientist", conversation_id="short1", user_id="sep_user2")
        # Different user should not see previous user's memory
        with patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock_resp("r2"))) as mock:
            await route_message("What should I learn next?", conversation_id="short2", user_id="sep_user_different")
            if mock.called:
                prompt = mock.call_args[0][0]
                # Should not contain Data Scientist from sep_user
                # It's okay if it contains from sep_user2, but not sep_user
                # Since we use sep_user_different, it should have no memory
                assert "Data Scientist" not in prompt or "User Profile" not in prompt
    asyncio.run(run())

# ---- Clearing memory ----
def test_clear_memory_single_user():
    mem.upsert_profile("u_clear", {"career_goal": "Test Goal"})
    assert mem.get_profile("u_clear") is not None
    mem.delete_profile("u_clear")
    assert mem.get_profile("u_clear") is None

def test_clear_all_memory():
    mem.upsert_profile("u1", {"career_goal": "Goal1"})
    mem.upsert_profile("u2", {"career_goal": "Goal2"})
    mem.clear_all()
    assert mem.get_profile("u1") is None
    assert mem.get_profile("u2") is None

def test_memory_api_crud():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        # Create via API
        resp = client.post("/api/memory/", json={"user_id": "api_user", "career_goal": "AI Engineer", "preferred_name": "Riya"})
        assert resp.status_code == 200, resp.text
        # Get
        resp = client.get("/api/memory/api_user")
        assert resp.status_code == 200
        assert resp.json()["profile"]["career_goal"] == "AI Engineer"
        # Update via PUT
        resp = client.put("/api/memory/api_user", json={"career_goal": "ML Engineer"})
        assert resp.status_code == 200
        assert resp.json()["profile"]["career_goal"] == "ML Engineer"
        # Get context
        resp = client.get("/api/memory/context/api_user")
        assert resp.status_code == 200
        assert "ML Engineer" in resp.json()["context"]
        # Delete
        resp = client.delete("/api/memory/api_user")
        assert resp.status_code == 200
        resp = client.get("/api/memory/api_user")
        assert resp.json()["exists"] is False

def test_memory_bounded_fields():
    # Name too long should be truncated
    long_name = "A" * 100
    mem.upsert_profile("u_bound", {"preferred_name": long_name})
    assert len(mem.get_profile("u_bound")["preferred_name"]) <= 50
    # Career goal too long
    long_goal = "B" * 200
    mem.upsert_profile("u_bound", {"career_goal": long_goal})
    assert len(mem.get_profile("u_bound")["career_goal"]) <= 120

def test_memory_editable_deletable_via_direct():
    mem.upsert_profile("u_edit", {"career_goal": "Initial", "preferred_name": "Bob"})
    mem.upsert_profile("u_edit", {"career_goal": "Updated"})
    assert mem.get_profile("u_edit")["career_goal"] == "Updated"
    assert mem.get_profile("u_edit")["preferred_name"] == "Bob"  # unchanged
    mem.delete_profile("u_edit")
    assert mem.get_profile("u_edit") is None

def test_persistence_across_restart():
    # Create profile, then simulate restart by closing and reopening connection (file persists)
    mem.upsert_profile("persist_user", {"career_goal": "Persistent Goal", "known_skills": ["Python"]})
    # Force write and close - already committed
    # Now directly open new connection to same DB_PATH and verify
    import sqlite3, json, os
    assert os.path.exists(mem.DB_PATH), f"DB file should exist at {mem.DB_PATH}"
    conn = sqlite3.connect(mem.DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_memory WHERE user_id = ?", ("persist_user",))
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert row["career_goal"] == "Persistent Goal"
    # Also via API after "restart" (re-import)
    fetched = mem.get_profile("persist_user")
    assert fetched["career_goal"] == "Persistent Goal"
    assert "Python" in fetched["known_skills"]

def test_default_user_memory_persists_across_conversations():
    import asyncio
    async def run():
        from app.services.orchestrator import route_message
        # Without explicit user_id, should use default_user and persist
        with patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock_resp("r"))):
            await route_message("I want to become a Generative AI Developer.", conversation_id="default_conv1")
        p = mem.get_profile(mem.DEFAULT_USER_ID)
        assert p is not None and p["career_goal"] == "Generative AI Developer"
        with patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock_resp("r"))) as mock:
            await route_message("What should I learn next?", conversation_id="default_conv2")
            assert mock.called
            prompt = mock.call_args[0][0]
            assert "Generative AI Developer" in prompt
    asyncio.run(run())
