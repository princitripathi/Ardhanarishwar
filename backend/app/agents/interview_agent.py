from typing import Dict

from app.services.llm import generate_response

SYSTEM_PROMPT = """You are the Interview Agent for Ardhanarishwar AI Assistant.

Your purpose is to help users with interview preparation including:
- Interview preparation
- Technical interview preparation
- Behavioral interview preparation
- Mock interview guidance
- Interview feedback guidance

Do not build a multi-turn interview state machine. Provide single-turn guidance only.

Provide clear interview tips, common questions, and preparation strategies. Never claim access to real interview databases or company-specific question banks. Base your advice on general interview best practices."""


async def get_response(message: str, conversation_history: str = None) -> Dict[str, str]:
    prompt = f"Recent conversation:\n{conversation_history}\n\nCurrent message: {message}" if conversation_history else message
    response = await generate_response(prompt, system_prompt=SYSTEM_PROMPT)
    return {"response": response.response, "intent": "interview", "agent": "interview"}


async def get_system_prompt() -> str:
    return SYSTEM_PROMPT


def get_name() -> str:
    return "Interview Coach"