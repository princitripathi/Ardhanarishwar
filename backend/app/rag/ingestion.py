from typing import Dict, List, Optional
import os

from app.rag.store import get_store
from app.services.security import (
    validate_doc_text,
    validate_title as sec_validate_title,
    validate_source as sec_validate_source,
    validate_doc_id as sec_validate_doc_id,
    MAX_DOCS_TOTAL,
)
from app.rag.store import get_store as _get_store_for_limit

# Document ingestion layer: text extraction -> chunking -> embeddings -> storage

ALLOWED_EXTENSIONS = {".txt", ".md"}  # start with text-based for reliability
MAX_FILE_BYTES = 100 * 1024  # 100KB for file bytes
ALLOWED_MIME = {"text/plain", "text/markdown", "text/x-markdown"}


def _validate_document(text: str, title: Optional[str] = None, source: Optional[str] = None, doc_id: Optional[str] = None):
    # Use centralized validators with size/type limits
    validate_doc_text(text)
    if title is not None:
        sec_validate_title(title)
    if source is not None:
        sec_validate_source(source)
    if doc_id is not None:
        sec_validate_doc_id(doc_id)
    # Enforce total docs limit to prevent unbounded memory growth
    store = _get_store_for_limit()
    if store.count() >= MAX_DOCS_TOTAL:
        raise ValueError(f"Document store limit reached ({MAX_DOCS_TOTAL}) — delete old documents first")


def ingest_document(text: str, title: str = None, source: str = None, doc_id: str = None) -> Dict:
    """Ingest a text document into local vector index.

    Returns metadata: {id, title, source, chunk_count, created_at}
    """
    _validate_document(text, title, source, doc_id)
    # Sanitize title/source as validated, pass through
    if title is not None:
        title = sec_validate_title(title) or title.strip()
    if source is not None:
        source = sec_validate_source(source) or source.strip()
    if doc_id is not None:
        doc_id = sec_validate_doc_id(doc_id) or doc_id.strip()
    store = get_store()
    doc = store.add_document(text=text.strip(), title=title, source=source, doc_id=doc_id)
    return doc


def ingest_text(text: str, title: str = None, source: str = None) -> Dict:
    """Alias for ingest_document (text-based)."""
    return ingest_document(text=text, title=title, source=source)


def ingest_file_content(content: bytes, filename: str, title: str = None, source: str = None, content_type: str = None) -> Dict:
    """Extract text from file bytes (text-based only for prototype)."""
    if content is None:
        raise ValueError("File content cannot be None")
    if not isinstance(content, bytes):
        raise ValueError("File content must be bytes")
    if not filename or not isinstance(filename, str):
        raise ValueError("Filename must be a non-empty string")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError(f"File too large (max {MAX_FILE_BYTES} bytes)")
    # Validate MIME if provided
    if content_type and content_type not in ALLOWED_MIME and "text" not in content_type.lower():
        raise ValueError(f"Unsupported content type {content_type}")
    # Sanitize filename: strip path, prevent traversal
    base = os.path.basename(filename.strip())
    if not base or base != filename.strip() or ".." in base or "/" in base or "\\" in base:
        # Use basename only
        base = os.path.basename(base) if base else "file.txt"
    _, ext = os.path.splitext(base.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")
    filename = base

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except Exception as e:
            raise ValueError(f"Failed to decode file: {e}")

    if not text.strip():
        raise ValueError("File is empty or contains no extractable text")

    return ingest_document(text=text, title=title or filename, source=source or filename)


def list_documents() -> List[Dict]:
    store = get_store()
    return store.list_documents()


def clear_documents() -> None:
    store = get_store()
    store.clear()


def get_document(doc_id: str) -> Optional[Dict]:
    store = get_store()
    return store.get_document(doc_id)
