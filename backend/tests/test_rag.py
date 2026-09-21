"""Phase 4 RAG tests — lightweight local RAG system.

Covers:
- document ingestion
- chunking
- embedding generation (via retrieval)
- local vector storage/index
- similarity retrieval
- empty retrieval fallback
- relevant retrieval
- context injection
- source/document metadata
- malformed documents
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.rag.chunking import chunk_text
from app.rag.ingestion import ingest_document, clear_documents, list_documents, ingest_file_content
from app.rag.store import get_store, reset_store
from app.rag.retrieval import retrieve, format_context, build_grounded_prompt
from app.services import conversation_memory as cm
from app.services.orchestrator import _last_intent


@pytest.fixture(autouse=True)
def clean_rag():
    reset_store()
    cm.clear_all()
    _last_intent.clear()
    clear_documents()
    yield
    reset_store()
    clear_documents()
    cm.clear_all()
    _last_intent.clear()


def mock_resp(text="Mocked response"):
    return type("obj", (), {"response": text, "model": "qwen2.5:3b"})()


# ---- Chunking ----
def test_chunking_single_short():
    text = "This is a short document."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunking_splits_long():
    # 1200 chars should split into ~3 chunks of 500 with 100 overlap
    text = " ".join(["word"] * 300)  # ~1500 chars
    chunks = chunk_text(text, chunk_size=500, overlap=100)
    assert len(chunks) >= 2
    # Each chunk within size
    for c in chunks:
        assert len(c) <= 500
        assert c.strip()
    # Overlap: second chunk should share some text with first
    assert "word" in chunks[0] and "word" in chunks[1]


def test_chunking_sentence_aware():
    text = "First sentence about leave policy. Second sentence about remote work. Third sentence about interviews. " * 10
    chunks = chunk_text(text, chunk_size=200, overlap=30)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= 200


def test_chunking_malformed_none():
    with pytest.raises(ValueError):
        chunk_text(None)


def test_chunking_malformed_empty():
    with pytest.raises(ValueError):
        chunk_text("   ")


def test_chunking_malformed_nonstring():
    with pytest.raises(ValueError):
        chunk_text(123)


def test_chunking_invalid_params():
    with pytest.raises(ValueError):
        chunk_text("valid text for test", chunk_size=10)  # too small
    with pytest.raises(ValueError):
        chunk_text("valid text for test", chunk_size=500, overlap=500)


# ---- Ingestion ----
def test_document_ingestion_basic():
    doc = ingest_document(text="This is a valid document about leave policy with enough length to be meaningful.", title="Test Doc", source="test.txt")
    assert doc["title"] == "Test Doc"
    assert doc["source"] == "test.txt"
    assert doc["chunk_count"] >= 1
    assert doc["id"] in [d["id"] for d in list_documents()]
    store = get_store()
    assert store.count() == 1
    assert store.chunk_count() >= 1


def test_document_ingestion_multiple():
    ingest_document(text="Document one about remote work policy and hybrid model with manager approval.", title="Doc1", source="doc1.txt")
    ingest_document(text="Document two about interview process with four stages and evaluation.", title="Doc2", source="doc2.txt")
    assert len(list_documents()) == 2
    store = get_store()
    assert store.chunk_count() >= 2


def test_document_ingestion_metadata():
    doc = ingest_document(text="Leave policy is 24 days per year with advance request via portal.", title="Policy", source="policy.txt")
    store = get_store()
    chunk_ids = doc["chunk_ids"]
    first_chunk = store.chunks[chunk_ids[0]]
    assert first_chunk["metadata"]["title"] == "Policy"
    assert first_chunk["metadata"]["source"] == "policy.txt"
    assert first_chunk["metadata"]["doc_id"] == doc["id"]


def test_malformed_document_empty():
    with pytest.raises(ValueError):
        ingest_document(text="   ", title="empty")


def test_malformed_document_none():
    with pytest.raises(ValueError):
        ingest_document(text=None)


def test_malformed_document_nonstring():
    with pytest.raises(ValueError):
        ingest_document(text=123)


def test_malformed_document_too_short():
    with pytest.raises(ValueError):
        ingest_document(text="short")


def test_ingest_file_content_text():
    content = b"This is file content about SampleCorp remote work hybrid model 3 days."
    doc = ingest_file_content(content, filename="test.txt", title="File Doc")
    assert doc["title"] == "File Doc"
    assert doc["chunk_count"] >= 1


def test_ingest_file_unsupported_type():
    with pytest.raises(ValueError):
        ingest_file_content(b"some text", filename="file.pdf")


def test_ingest_file_empty():
    with pytest.raises(ValueError):
        ingest_file_content(b"   ", filename="empty.txt")


# ---- Embeddings implicitly via retrieval; direct test ----
def test_embedding_generation_via_store():
    ingest_document(text="Employees may work remotely up to 3 days per week with manager approval.", title="Remote", source="remote.txt")
    store = get_store()
    # Vectors should be created for chunks
    assert len(store.vectors) == store.chunk_count()
    for vec in store.vectors.values():
        assert isinstance(vec, dict)
        # Vectors are L2 normalized dicts, values should be >0 <1
        if vec:
            for v in vec.values():
                assert 0 < v <= 1.0


# ---- Retrieval ----
def test_relevant_retrieval():
    ingest_document(text="Employees at SampleCorp are entitled to 24 days of paid annual leave per year. Leave must be requested 7 days in advance via HR portal.", title="Leave Policy", source="sample_company_policy.txt")
    ingest_document(text="SampleCorp recruitment process has 4 stages for hiring developers.", title="Other", source="other.txt")
    results = retrieve("How many paid leave days per year?", top_k=2)
    assert len(results) >= 1
    # Top result should be Leave Policy
    top = results[0]
    assert "Leave Policy" in top["metadata"]["title"]
    assert top["score"] > 0.1
    assert "24 days" in top["text"] or "annual leave" in top["text"].lower()


def test_retrieval_empty_index():
    results = retrieve("Any query about leave policy")
    assert results == []


def test_retrieval_no_relevant_docs():
    ingest_document(text="Leave policy is 24 days annual leave. Remote work up to 3 days per week.", title="Policy", source="policy.txt")
    results = retrieve("What is quantum physics entanglement?", top_k=3, threshold=0.12)
    # Query unrelated to docs should return empty or low score
    assert results == [] or all(r["score"] < 0.12 for r in results)


def test_retrieval_threshold_filters():
    ingest_document(text="Remote work hybrid model 3 days per week with manager approval.", title="Remote", source="remote.txt")
    # Low threshold should return results for somewhat relevant query
    low = retrieve("remote work days per week", top_k=3, threshold=0.05)
    assert len(low) >= 1
    # High threshold should filter out weak matches
    high = retrieve("remote work days per week", top_k=3, threshold=0.9)
    # Might be empty if top score <0.9
    assert len(high) <= len(low)


def test_retrieval_source_metadata():
    ingest_document(text="SampleCorp interview has 4 stages: Resume Screening, Technical Round, Managerial Round, HR Discussion.", title="Interview Sample", source="sample.txt")
    results = retrieve("How many interview stages?", top_k=1)
    assert len(results) == 1
    assert results[0]["metadata"]["title"] == "Interview Sample"
    assert results[0]["metadata"]["source"] == "sample.txt"
    assert "doc_id" in results[0]["metadata"]
    assert "chunk_id" in results[0]
    assert "score" in results[0]


# ---- Context injection ----
def test_context_injection_relevant():
    import asyncio
    ingest_document(text="Remote work policy at SampleCorp is hybrid up to 3 days per week with manager approval. Core hours 11 AM to 3 PM IST.", title="Remote Policy Sample", source="sample_policy.txt")

    async def run():
        with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_resp("general grounded reply"))) as mock_gen:
            from app.services.orchestrator import route_message
            result = await route_message("What is the remote work policy at SampleCorp?", conversation_id="rag-test-1")
            assert result.get("rag_used") is True or result.get("rag_count") >= 1
            assert result.get("rag_sources") is not None
            assert len(result.get("rag_sources", [])) >= 1
            assert mock_gen.called
            prompt_arg = mock_gen.call_args[0][0]
            assert "Remote Policy Sample" in prompt_arg or "remote" in prompt_arg.lower() or "3 days" in prompt_arg

    asyncio.run(run())


def test_context_injection_no_relevant():
    import asyncio
    ingest_document(text="Leave policy 24 days annual leave. This is sufficient length to be valid document.", title="Leave", source="leave.txt")

    async def run():
        with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_resp("general reply"))) as mock_gen:
            from app.services.orchestrator import route_message
            result = await route_message("Explain quantum entanglement in simple terms", conversation_id="rag-test-2")
            assert result.get("rag_used") is False or result.get("rag_count") == 0
            # For general intent, mock_gen should be called; check fallback note
            if mock_gen.called:
                prompt = mock_gen.call_args[0][0]
                assert "No relevant documents" in prompt or "approved" in prompt.lower()

    asyncio.run(run())


def test_context_injection_specialized_agent_receives_rag():
    import asyncio
    ingest_document(text="SampleCorp interview process has 4 stages and evaluates technical accuracy, communication, depth, clarity.", title="Interview Doc", source="interview.txt")

    async def run():
        with patch("app.agents.interview_agent.generate_response", new=AsyncMock(return_value=mock_resp("interview reply"))) as mock_int:
            from app.services.orchestrator import route_message
            result = await route_message("Tell me about the interview process stages", conversation_id="rag-test-3")
            assert mock_int.called
            prompt = mock_int.call_args[0][0]
            assert "Interview Doc" in prompt or "4 stages" in prompt

    asyncio.run(run())


def test_build_grounded_prompt_with_results():
    ingest_document(text="SampleCorp leave 24 days per year via HR portal.", title="Leave Sample", source="sample.txt")
    results = retrieve("leave days per year", top_k=1)
    assert len(results) >= 1
    prompt = build_grounded_prompt("How many leave days?", results)
    assert "Relevant documents" in prompt or "Leave Sample" in prompt
    assert "How many leave days?" in prompt


def test_build_grounded_prompt_empty_fallback():
    prompt = build_grounded_prompt("What is remote work policy?", [])
    assert "No relevant documents were found" in prompt
    assert "Do not fabricate" in prompt


# ---- Malformed documents (ingestion) ----
def test_malformed_file_none_content():
    with pytest.raises(ValueError):
        ingest_file_content(None, filename="test.txt")


def test_malformed_file_nonbytes():
    with pytest.raises(ValueError):
        ingest_file_content("not bytes", filename="test.txt")


def test_malformed_filename_empty():
    with pytest.raises(ValueError):
        ingest_file_content(b"some content that is long enough", filename="")


# ---- Empty retrieval handling in API ----
def test_retrieval_fallback_api_behavior():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        clear_documents()
        resp = client.post("/api/rag/query", json={"query": "test query"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_results"] is False
        assert data["count"] == 0
        client.post("/api/rag/ingest", json={"text": "Remote work up to 3 days per week at SampleCorp with manager approval, core hours 11-3. This document has sufficient length.", "title": "Policy", "source": "policy.txt"})
        resp2 = client.post("/api/rag/query", json={"query": "remote work days"})
        assert resp2.status_code == 200
        assert resp2.json()["has_results"] is True


def test_rag_stats_and_clear():
    ingest_document(text="Document for stats with enough length to be valid and meaningful content about testing.", title="Stats Doc", source="stats.txt")
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        stats = client.get("/api/rag/stats").json()
        assert stats["document_count"] >= 1
        # Clear
        client.post("/api/rag/clear")
        stats2 = client.get("/api/rag/stats").json()
        assert stats2["document_count"] == 0


# ---- Distinguish retrieved from general knowledge ----
def test_distinguish_retrieved_vs_general():
    ingest_document(text="SampleCorp remote policy hybrid 3 days per week. Core hours 11 AM to 3 PM IST. This is sufficient length to be valid document for testing purposes.", title="Remote Sample", source="sample.txt")
    results = retrieve("remote work policy SampleCorp", top_k=1)
    ctx = format_context(results)
    assert "Source:" in ctx
    assert "Distinguish" in ctx or "distinguish" in ctx.lower() or "Retrieved" in ctx
    prompt = build_grounded_prompt("What is remote policy?", results)
    assert "Distinguish" in prompt or "distinguish" in prompt.lower()


def test_ingest_duplicate_doc_id():
    ingest_document(text="First document content with enough length to be valid for testing purposes.", title="First", source="first.txt", doc_id="custom-id")
    with pytest.raises(ValueError):
        ingest_document(text="Second document with same id but different content for testing.", title="Second", source="second.txt", doc_id="custom-id")
