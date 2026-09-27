import json
import os
import time
import logging
from typing import AsyncGenerator, Optional
import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT_MS = int(os.getenv("OLLAMA_TIMEOUT_MS", "180000"))
OLLAMA_TIMEOUT_S = OLLAMA_TIMEOUT_MS / 1000.0
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "512"))
OLLAMA_NUM_PREDICT_INTENT = {
    "general": 1024,
    "career": 1024,
    "resume": 1024,
    "interview": 1024,
    "learning": 1024,
    "recruitment": 1024,
    "business": 1024,
}
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")

# Health/model cache to avoid duplicate /api/tags calls per request (Phase 8).
# Measurements show health ~700ms + model ~680ms = 1.4s overhead per generate call.
# Cache for HEALTH_CACHE_TTL seconds; combines both checks into single HTTP call when miss.
HEALTH_CACHE_TTL = 10.0
_health_cache: dict = {"timestamp": 0.0, "healthy": False, "models": [], "last_fetch": 0.0}

SYSTEM_PROMPT = """You are Ardhanarishwar Solver, the general assistant for the Ardhanarishwar Solver AI platform (local Qwen 2.5 3B via Ollama).

Provide useful, accurate help across career, education, professional development, recruitment, business and general topics. Be actionable when helpful and concise when the question is simple. If the request is ambiguous or lacks needed detail, ask 1-2 clarifying questions. Never claim live browsing, live data, or verified proprietary databases."""




class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    model: str
    done_reason: Optional[str] = None


class OllamaError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def _fetch_tags_cached(force: bool = False) -> dict:
    """Fetch /api/tags once and populate cache. Returns {healthy, models}."""
    now = time.monotonic()
    # Use cache if fresh
    if not force and (now - _health_cache["timestamp"] < HEALTH_CACHE_TTL) and _health_cache["healthy"]:
        return {"healthy": _health_cache["healthy"], "models": _health_cache["models"]}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            healthy = response.status_code == 200
            models = []
            if healthy:
                try:
                    data = response.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                except Exception:
                    pass
            _health_cache["timestamp"] = now
            _health_cache["healthy"] = healthy
            _health_cache["models"] = models
            return {"healthy": healthy, "models": models}
    except httpx.RequestError as e:
        logger.error(f"Ollama health check failed: {e}")
        # On failure, cache short negative to avoid hammering but allow retry quickly
        _health_cache["timestamp"] = now - (HEALTH_CACHE_TTL - 2.0)  # retry after ~2s
        _health_cache["healthy"] = False
        return {"healthy": False, "models": []}


async def check_ollama_health() -> bool:
    result = await _fetch_tags_cached()
    return result["healthy"]


async def is_model_available(model: str = OLLAMA_MODEL) -> bool:
    result = await _fetch_tags_cached()
    if not result["healthy"]:
        return False
    return model in result["models"]


def clear_health_cache() -> None:
    """For testing: invalidate cache."""
    _health_cache["timestamp"] = 0.0
    _health_cache["healthy"] = False
    _health_cache["models"] = []


def get_num_predict(intent: Optional[str] = None) -> int:
    """Get num_predict for an intent, falling back to global default."""
    if intent and intent in OLLAMA_NUM_PREDICT_INTENT:
        return OLLAMA_NUM_PREDICT_INTENT[intent]
    return OLLAMA_NUM_PREDICT


async def generate_response(message: str, system_prompt: Optional[str] = None, num_predict: Optional[int] = None) -> ChatResponse:
    if not message or not message.strip():
        raise OllamaError("Message cannot be empty", 400)

    prompt_text = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    if num_predict is None:
        num_predict = OLLAMA_NUM_PREDICT

    if not await check_ollama_health():
        logger.error(f"Ollama health check failed - base URL: {OLLAMA_BASE_URL}")
        raise OllamaError("Ollama service is unavailable", 503)

    if not await is_model_available():
        logger.error(f"Model {OLLAMA_MODEL} not available on Ollama at {OLLAMA_BASE_URL}")
        raise OllamaError(f"Model {OLLAMA_MODEL} is not available", 503)

    payload = {
        "model": OLLAMA_MODEL,
        "system": prompt_text,
        "prompt": message.strip(),
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"num_predict": num_predict},
    }

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_S) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload,
            )
    except httpx.TimeoutException:
        logger.error(f"Ollama request timed out after {OLLAMA_TIMEOUT_S}s - base URL: {OLLAMA_BASE_URL}")
        raise OllamaError("Request timed out", 504)
    except httpx.RequestError as e:
        logger.error(f"Ollama request failed - base URL: {OLLAMA_BASE_URL}, error: {e}")
        raise OllamaError("Failed to connect to Ollama", 503)

    if response.status_code != 200:
        logger.error(f"Ollama returned error: {response.status_code} - {response.text[:500]}")
        raise OllamaError("Ollama returned an error", 502)

    try:
        data = response.json()
        response_text = data.get("response", "").strip()
        if not response_text:
            raise OllamaError("Empty response from model", 502)
        return ChatResponse(response=response_text, model=OLLAMA_MODEL, done_reason=data.get("done_reason"))
    except ValueError as e:
        logger.error(f"Failed to parse Ollama response: {e}")
        raise OllamaError("Invalid response from Ollama", 502)


async def generate_response_stream(
    message: str, system_prompt: Optional[str] = None, num_predict: Optional[int] = None
) -> AsyncGenerator[str, None]:
    if not message or not message.strip():
        raise OllamaError("Message cannot be empty", 400)

    prompt_text = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    if num_predict is None:
        num_predict = OLLAMA_NUM_PREDICT

    if not await check_ollama_health():
        logger.error(f"Ollama health check failed (stream) - base URL: {OLLAMA_BASE_URL}")
        raise OllamaError("Ollama service is unavailable", 503)

    if not await is_model_available():
        logger.error(f"Model {OLLAMA_MODEL} not available on Ollama at {OLLAMA_BASE_URL} (stream)")
        raise OllamaError(f"Model {OLLAMA_MODEL} is not available", 503)

    payload = {
        "model": OLLAMA_MODEL,
        "system": prompt_text,
        "prompt": message.strip(),
        "stream": True,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"num_predict": num_predict},
    }

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_S) as client:
            async with client.stream(
                "POST", f"{OLLAMA_BASE_URL}/api/generate", json=payload
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    logger.error(
                        f"Ollama stream returned error: {response.status_code} - {body[:500]}"
                    )
                    raise OllamaError("Ollama returned an error", 502)
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith('{"response":""'):
                        continue
                    try:
                        data = json.loads(line)
                    except ValueError:
                        continue
                    chunk = data.get("response", "")
                    done_reason = data.get("done_reason")
                    if chunk:
                        yield {"content": chunk, "done_reason": done_reason}
                    elif done_reason:
                        yield {"content": "", "done_reason": done_reason}
                    if data.get("done"):
                        break
    except httpx.TimeoutException:
        logger.error(f"Ollama stream request timed out after {OLLAMA_TIMEOUT_S}s - base URL: {OLLAMA_BASE_URL}")
        raise OllamaError("Stream request timed out", 504)
    except httpx.RequestError as e:
        logger.error(f"Ollama stream request failed - base URL: {OLLAMA_BASE_URL}, error: {e}")
        raise OllamaError("Failed to connect to Ollama", 503)