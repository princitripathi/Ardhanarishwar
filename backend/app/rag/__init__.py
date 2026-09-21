"""Lightweight RAG system for Ardhanarishwar Solver (Phase 4 - prototype).

Design goals:
- Keep chat/agent architecture unchanged
- No external AI APIs, no Ollama replacement
- Prototype-level, maintainable, no distributed vector DB
- Local TF-IDF embeddings + in-memory cosine retrieval
- Text-based documents only for reliability

Flow:
Document -> Text extraction -> Chunking -> Embeddings -> Local vector index -> Retrieval -> Relevant context -> Existing agent -> Qwen -> Grounded response

If no relevant context found, fallback: do not fabricate company information, answer from general knowledge with clear distinction.
"""

from app.rag.chunking import chunk_text
from app.rag.store import get_store, VectorStore
from app.rag.retrieval import retrieve, retrieve_with_threshold
from app.rag.ingestion import ingest_document, ingest_text, list_documents, clear_documents

__all__ = [
    "chunk_text",
    "get_store",
    "VectorStore",
    "retrieve",
    "retrieve_with_threshold",
    "ingest_document",
    "ingest_text",
    "list_documents",
    "clear_documents",
]
