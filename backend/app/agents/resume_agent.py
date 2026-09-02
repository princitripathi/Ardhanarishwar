from typing import Dict

from app.services.llm import generate_response

SYSTEM_PROMPT = """You are the Resume Agent for Ardhanarishwar AI Assistant.

Your purpose is to help users with resume and CV-related guidance including:
- Resume improvement guidance
- CV structure and formatting
- ATS-oriented recommendations
- Resume writing guidance

For now, you receive only text-based input. Do not implement file upload.

Provide practical, ATS-friendly resume advice. Never claim access to proprietary resume databases or ATS scoring systems. Base your guidance on general best practices and clearly indicate when you're providing general recommendations."""


async def get_response(message: str, conversation_history: str = None) -> Dict[str, str]:
    prompt = f"Recent conversation:\n{conversation_history}\n\nCurrent message: {message}" if conversation_history else message
    response = await generate_response(prompt, system_prompt=SYSTEM_PROMPT)
    return {"response": response.response, "intent": "resume", "agent": "resume"}


async def get_system_prompt() -> str:
    return SYSTEM_PROMPT


def get_name() -> str:
    return "Resume Advisor"