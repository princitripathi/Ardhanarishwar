from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator
from typing import Optional, List

from app.rag.ingestion import ingest_document, list_documents, clear_documents, get_document
from app.rag.store import get_store
from app.rag.retrieval import retrieve
from app.services.security import (
    validate_doc_text,
    validate_title,
    validate_source,
    validate_doc_id,
    sanitize_for_log,
    ingest_limiter,
    get_client_key,
)

router = APIRouter(prefix="/api/rag", tags=["rag"])


class IngestRequest(BaseModel):
    text: str
    title: Optional[str] = None
    source: Optional[str] = None
    doc_id: Optional[str] = None

    @field_validator("text")
    @classmethod
    def check_text(cls, v):
        return validate_doc_text(v)

    @field_validator("title")
    @classmethod
    def check_title(cls, v):
        if v is None:
            return v
        return validate_title(v) or v

    @field_validator("source")
    @classmethod
    def check_source(cls, v):
        if v is None:
            return v
        return validate_source(v) or v

    @field_validator("doc_id")
    @classmethod
    def check_doc_id(cls, v):
        if v is None:
            return v
        return validate_doc_id(v) or v


class QueryRequest(BaseModel):
    query: str
    top_k: int = 3
    threshold: float = 0.12

    @field_validator("query")
    @classmethod
    def check_query(cls, v):
        if not v or not v.strip():
            raise ValueError("Query cannot be empty")
        if len(v.strip()) > 2000:
            raise ValueError("Query too long (max 2000)")
        return v.strip()

    @field_validator("top_k")
    @classmethod
    def check_top_k(cls, v):
        if not isinstance(v, int) or v < 1 or v > 10:
            raise ValueError("top_k must be 1-10")
        return v

    @field_validator("threshold")
    @classmethod
    def check_thresh(cls, v):
        if not isinstance(v, (int, float)) or v < 0 or v > 1:
            raise ValueError("threshold must be 0-1")
        return float(v)


@router.post("/ingest")
async def ingest(req: IngestRequest, request: Request):
    # Rate limit ingest
    key = get_client_key(request)
    allowed, retry_after = ingest_limiter.is_allowed(key)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Too many requests. Try again in {retry_after}s")
    try:
        doc = ingest_document(text=req.text, title=req.title, source=req.source, doc_id=req.doc_id)
        return {"status": "ok", "document": doc}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=sanitize_for_log(str(e), 300))
    except Exception as e:
        # Do not expose internal stack
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/query")
async def query(req: QueryRequest):
    # Validation already via Pydantic
    results = retrieve(req.query, top_k=req.top_k, threshold=req.threshold)
    return {"query": req.query, "results": results, "count": len(results), "has_results": len(results) > 0}


@router.get("/documents")
async def list_docs():
    docs = list_documents()
    return {"documents": docs, "count": len(docs)}


@router.get("/documents/{doc_id}")
async def get_doc(doc_id: str):
    # Validate doc_id to prevent traversal
    from app.services.security import is_valid_id
    if not is_valid_id(doc_id, 64):
        raise HTTPException(status_code=400, detail="Invalid document id")
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/documents/{doc_id}")
async def delete_doc(doc_id: str):
    from app.services.security import is_valid_id
    if not is_valid_id(doc_id, 64):
        raise HTTPException(status_code=400, detail="Invalid document id")
    store = get_store()
    ok = store.delete_document(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted", "doc_id": doc_id}


@router.post("/clear")
async def clear():
    clear_documents()
    return {"status": "cleared"}


@router.get("/stats")
async def stats():
    store = get_store()
    return {"document_count": store.count(), "chunk_count": store.chunk_count()}
