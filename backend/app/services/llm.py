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


async def generate_response(message: str, system_prompt: Optional[str] = None) -> ChatResponse:
    if not message or not message.strip():
        raise OllamaError("Message cannot be empty", 400)

    if not await check_ollama_health():
        raise OllamaError("Ollama service is unavailable", 503)

    if not await is_model_available():
        raise OllamaError(f"Model {OLLAMA_MODEL} is not available", 503)

    prompt_text = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"{prompt_text}\n\nUser: {message.strip()}\n\nAssistant:",
        "stream": False,
        "keep_alive": "30m",
        "options": {"num_predict": 250},
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload,
            )
    except httpx.TimeoutException:
        logger.error("Ollama request timed out")
        raise OllamaError("Request timed out", 504)
    except httpx.RequestError as e:
        logger.error(f"Ollama request failed: {e}")
        raise OllamaError("Failed to connect to Ollama", 503)

    if response.status_code != 200:
        logger.error(f"Ollama returned error: {response.status_code} - {response.text}")
        raise OllamaError("Ollama returned an error", 502)

    try:
        data = response.json()
        response_text = data.get("response", "").strip()
        if not response_text:
            raise OllamaError("Empty response from model", 502)
        return ChatResponse(response=response_text, model=OLLAMA_MODEL)
    except ValueError as e:
        logger.error(f"Failed to parse Ollama response: {e}")
        raise OllamaError("Invalid response from Ollama", 502)


async def generate_response_stream(
    message: str, system_prompt: Optional[str] = None
) -> AsyncGenerator[str, None]:
    if not message or not message.strip():
        raise OllamaError("Message cannot be empty", 400)

    if not await check_ollama_health():
        raise OllamaError("Ollama service is unavailable", 503)

    if not await is_model_available():
        raise OllamaError(f"Model {OLLAMA_MODEL} is not available", 503)

    prompt_text = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"{prompt_text}\n\nUser: {message.strip()}\n\nAssistant:",
        "stream": True,
        "keep_alive": "30m",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
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
                    try:
                        data = json.loads(line)
                    except ValueError:
                        continue
                    chunk = data.get("response", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
    except httpx.RequestError as e:
        logger.error(f"Ollama stream request failed: {e}")
        raise OllamaError("Failed to connect to Ollama", 503)