import json
import logging
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from app.services.llm import OllamaError
from app.services.orchestrator import route_message, stream_message
from app.interview.routes import router as interview_router
from app.interview.session_routes import router as session_router
from app.interview.service import init_db as init_interview_db
from app.interview.session_service import init_session_db
from app.rag.routes import router as rag_router
from app.services.memory_routes import router as memory_router
from app.services.user_memory import init_db as init_memory_db
from app.services.security import (
    get_allowed_origins,
    sanitize_for_log,
    validate_message,
    is_valid_id,
    chat_limiter,
    get_client_key,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Ardhanarishwar Solver Backend")

# Initialize interview DB and user memory DB
try:
    init_interview_db()
    init_session_db()
    init_memory_db()
    logger.info("Interview DB and Memory DB initialized")
except Exception as e:
    # Do not log raw exception with potential sensitive path info verbatim
    logger.warning(f"DB init failed: {sanitize_for_log(str(e), 300)}")

# CORS: env-configurable, tight methods/headers for internal use
allowed_origins = get_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "no-referrer"
    # Minimal CSP for API — frontend handles UI CSP
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    return response


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    user_id: str | None = None

    @field_validator("message")
    @classmethod
    def validate_message_field(cls, v: str) -> str:
        return validate_message(v)

    @field_validator("conversation_id")
    @classmethod
    def validate_conv_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("conversation_id must be a string")
        v = v.strip()
        if not v:
            return None
        if len(v) > 64:
            raise ValueError("conversation_id too long (max 64)")
        if not is_valid_id(v, 64):
            raise ValueError("conversation_id contains invalid characters")
        return v

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("user_id must be a string")
        v = v.strip()
        if not v:
            return None
        if len(v) > 64:
            raise ValueError("user_id too long (max 64)")
        if not is_valid_id(v, 64):
            raise ValueError("user_id contains invalid characters")
        return v


class ChatResponse(BaseModel):
    response: str
    model: str = "qwen2.5:3b"
    intent: str
    agent: str | None = None
    routing_reason: str | None = None
    conversation_id: str | None = None
    rag_used: bool | None = None
    rag_sources: list | None = None
    rag_count: int | None = None


@app.get("/")
async def root():
    return {"service": "ardhanarishwar-backend", "message": "Backend is running"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ardhanarishwar-backend"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    # Basic rate limiting (prototype): 30/min per IP
    key = get_client_key(request)
    allowed, retry_after = chat_limiter.is_allowed(key)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Too many requests. Try again in {retry_after}s")
    # Pydantic already validated message length etc.
    try:
        result = await route_message(body.message.strip(), conversation_id=body.conversation_id, user_id=body.user_id)
        return ChatResponse(
            response=result["response"],
            intent=result["intent"],
            agent=result.get("agent"),
            routing_reason=result.get("routing_reason"),
            conversation_id=result.get("conversation_id"),
            rag_used=result.get("rag_used"),
            rag_sources=result.get("rag_sources"),
            rag_count=result.get("rag_count"),
        )
    except OllamaError as e:
        # Use existing error handling without exposing stack traces
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.exception("Unexpected error in chat endpoint")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/chat/stream")
async def chat_stream(body: ChatRequest, request: Request):
    # Rate limit streaming as well
    key = get_client_key(request)
    allowed, retry_after = chat_limiter.is_allowed(key)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Too many requests. Try again in {retry_after}s")

    async def event_generator():
        try:
            async for event in stream_message(body.message.strip(), conversation_id=body.conversation_id, user_id=body.user_id):
                yield json.dumps(event) + "\n"
        except OllamaError as e:
            yield json.dumps({"type": "error", "detail": e.message}) + "\n"
        except Exception:
            logger.exception("Unexpected error in stream endpoint")
            yield json.dumps({"type": "error", "detail": "Internal server error"}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


app.include_router(interview_router)
app.include_router(session_router)
app.include_router(rag_router)
app.include_router(memory_router)