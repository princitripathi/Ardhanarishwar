import pytest
from app.services import user_memory as mem
from app.services import conversation_memory as cm
from app.services.orchestrator import _last_intent

@pytest.fixture(autouse=True)
def isolate_state():
    # Clear before each test to ensure isolation
    try:
        mem.clear_all()
        mem.clear_memory_cache()
    except Exception:
        pass
    cm.clear_all()
    _last_intent.clear()
    try:
        from app.rag.retrieval import clear_retrieval_cache
        clear_retrieval_cache()
    except Exception:
        pass
    try:
        from app.services.llm import clear_health_cache
        clear_health_cache()
    except Exception:
        pass
    try:
        from app.services.security import chat_limiter, ingest_limiter, interview_limiter
        chat_limiter.clear()
        ingest_limiter.clear()
        interview_limiter.clear()
    except Exception:
        pass
    yield
    try:
        mem.clear_all()
        mem.clear_memory_cache()
    except Exception:
        pass
    cm.clear_all()
    _last_intent.clear()
    try:
        from app.rag.retrieval import clear_retrieval_cache
        clear_retrieval_cache()
    except Exception:
        pass
    try:
        from app.services.llm import clear_health_cache
        clear_health_cache()
    except Exception:
        pass
    try:
        from app.services.security import chat_limiter, ingest_limiter, interview_limiter
        chat_limiter.clear()
        ingest_limiter.clear()
        interview_limiter.clear()
    except Exception:
        pass
