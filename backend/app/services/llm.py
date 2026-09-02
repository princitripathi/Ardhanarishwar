import json
import os
import logging
from typing import AsyncGenerator, Optional
import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

SYSTEM_PROMPT = """You are Ardhanarishwar AI Assistant.

Provide useful answers. Be clear and concise. Avoid pretending to have capabilities you do not have. Focus on career, education, professional development, recruitment, business and related assistance. Ask for clarification when the user's request is ambiguous."""


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


async def check_ollama_health() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return response.status_code == 200
    except httpx.RequestError as e:
        logger.error(f"Ollama health check failed: {e}")
        return False


async def is_model_available(model: str = OLLAMA_MODEL) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                return model in models
    except httpx.RequestError as e:
        logger.error(f"Model availability check failed: {e}")
    return False


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
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
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
        async with httpx.AsyncClient(timeout=None) as client:
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