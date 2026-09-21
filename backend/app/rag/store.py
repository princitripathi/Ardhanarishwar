import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional

from app.rag.chunking import chunk_text
from app.rag.embeddings import TfidfEmbedder

# In-memory local vector index (prototype, no external DB)
# Stored process-scoped, bounded for maintainability

class VectorStore:
    """Simple in-memory vector store.

    Stores documents -> chunks -> tf-idf vectors.
    No persistence beyond process (fits Current Limitations).
    """

    def __init__(self):
        self.documents: Dict[str, Dict] = {}  # doc_id -> {id, title, source, text, created_at, chunk_ids}
        self.chunks: Dict[str, Dict] = {}  # chunk_id -> {id, doc_id, text, metadata}
        self.vectors: Dict[str, Dict[str, float]] = {}  # chunk_id -> vector dict
        self.embedder: TfidfEmbedder = TfidfEmbedder()

    def clear(self) -> None:
        self.documents.clear()
        self.chunks.clear()
        self.vectors.clear()
        self.embedder = TfidfEmbedder()
        # Invalidate retrieval cache (Phase 8) if available
        try:
            from app.rag.retrieval import clear_retrieval_cache
            clear_retrieval_cache()
        except Exception:
            pass

    def add_document(self, text: str, title: str = None, source: str = None, doc_id: str = None) -> Dict:
        """Ingest document text, chunk, embed, store. Returns document metadata."""
        if text is None or not isinstance(text, str) or not text.strip():
            raise ValueError("Document text must be a non-empty string")
        if title is not None and not isinstance(title, str):
            raise ValueError("title must be a string")
        if source is not None and not isinstance(source, str):
            raise ValueError("source must be a string")

        doc_id = doc_id or str(uuid.uuid4())
        if doc_id in self.documents:
            raise ValueError(f"Document id already exists: {doc_id}")

        title = title or f"Document {doc_id[:8]}"
        source = source or "unknown"

        # Chunking (validates text)
        chunks = chunk_text(text)

        # Create document entry
        created_at = datetime.now(timezone.utc).isoformat()
        chunk_ids = []
        for idx, c in enumerate(chunks):
            cid = f"{doc_id}_{idx}"
            chunk_ids.append(cid)
            self.chunks[cid] = {
                "id": cid,
                "doc_id": doc_id,
                "text": c,
                "chunk_index": idx,
                "metadata": {
                    "title": title,
                    "source": source,
                    "doc_id": doc_id,
                    "chunk_index": idx,
                },
            }

        self.documents[doc_id] = {
            "id": doc_id,
            "title": title,
            "source": source,
            "text": text.strip(),
            "created_at": created_at,
            "chunk_ids": chunk_ids,
            "chunk_count": len(chunk_ids),
        }

        # Re-fit embedder on all chunks and recompute vectors
        # For prototype, refit is okay (small corpus). Keeps idf accurate.
        all_chunk_texts = [self.chunks[cid]["text"] for cid in self.chunks]
        self.embedder.fit(all_chunk_texts)
        # Recompute all vectors
        self.vectors.clear()
        for cid, chunk in self.chunks.items():
            self.vectors[cid] = self.embedder.vectorize(chunk["text"])
        # Invalidate retrieval cache
        try:
            from app.rag.retrieval import clear_retrieval_cache
            clear_retrieval_cache()
        except Exception:
            pass
        return self.documents[doc_id]

    def get_document(self, doc_id: str) -> Optional[Dict]:
        return self.documents.get(doc_id)

    def list_documents(self) -> List[Dict]:
        return list(self.documents.values())

    def count(self) -> int:
        return len(self.documents)

    def chunk_count(self) -> int:
        return len(self.chunks)

    def delete_document(self, doc_id: str) -> bool:
        if doc_id not in self.documents:
            return False
        chunk_ids = self.documents[doc_id]["chunk_ids"]
        for cid in chunk_ids:
            self.chunks.pop(cid, None)
            self.vectors.pop(cid, None)
        self.documents.pop(doc_id, None)
        # Refit embedder if remaining chunks
        if self.chunks:
            all_chunk_texts = [c["text"] for c in self.chunks.values()]
            self.embedder.fit(all_chunk_texts)
            self.vectors.clear()
            for cid, chunk in self.chunks.items():
                self.vectors[cid] = self.embedder.vectorize(chunk["text"])
        else:
            self.embedder = TfidfEmbedder()
        try:
            from app.rag.retrieval import clear_retrieval_cache
            clear_retrieval_cache()
        except Exception:
            pass
        return True


# Global singleton for app usage (keeps import simplicity)
_store: Optional[VectorStore] = None


def get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


def reset_store() -> None:
    """For testing: reset global singleton."""
    global _store
    if _store is not None:
        _store.clear()
    else:
        _store = VectorStore()
