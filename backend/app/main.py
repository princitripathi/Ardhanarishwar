import json
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.llm import OllamaError
from app.services.orchestrator import route_message, stream_message
from app.interview.routes import router as interview_router
from app.interview.session_routes import router as session_router
from app.interview.service import init_db as init_interview_db
from app.interview.session_service import init_session_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Ardhanarishwar Backend")

# Initialize interview DB
try:
    init_interview_db()
    init_session_db()
    logger.info("Interview DB initialized")
except Exception as e:
    logger.warning(f"Interview DB init failed: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    model: str = "qwen2.5:3b"
    intent: str
    agent: str | None = None
    routing_reason: str | None = None
    conversation_id: str | None = None


@app.get("/")
async def root():
    return {"service": "ardhanarishwar-backend", "message": "Backend is running"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ardhanarishwar-backend"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        result = await route_message(request.message.strip(), conversation_id=request.conversation_id)
        return ChatResponse(
            response=result["response"],
            intent=result["intent"],
            agent=result.get("agent"),
            routing_reason=result.get("routing_reason"),
            conversation_id=result.get("conversation_id"),
        )
    except OllamaError as e:
        # Use existing error handling without exposing stack traces
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.exception("Unexpected error in chat endpoint")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    async def event_generator():
        try:
            async for event in stream_message(request.message.strip(), conversation_id=request.conversation_id):
                yield json.dumps(event) + "\n"
        except OllamaError as e:
            yield json.dumps({"type": "error", "detail": e.message}) + "\n"
        except Exception:
            logger.exception("Unexpected error in stream endpoint")
            yield json.dumps({"type": "error", "detail": "Internal server error"}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


app.include_router(interview_router)
app.include_router(session_router)