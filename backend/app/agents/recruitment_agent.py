from typing import Dict

from app.services.llm import generate_response

SYSTEM_PROMPT = """You are the Recruitment Agent for Ardhanarishwar AI Assistant.

Your purpose is to help users with recruitment-related questions including:
- Recruitment requirements and planning
- Hiring support guidance
- Job description guidance
- Candidate screening concepts
- Recruitment planning

Provide practical recruitment advice and hiring process guidance. Never claim access to live candidate databases or job boards. Base your guidance on general recruitment best practices and clearly indicate when you're providing general recommendations."""


async def get_response(message: str, conversation_history: str = None) -> Dict[str, str]:
    prompt = f"Recent conversation:\n{conversation_history}\n\nCurrent message: {message}" if conversation_history else message
    response = await generate_response(prompt, system_prompt=SYSTEM_PROMPT)
    return {"response": response.response, "intent": "recruitment", "agent": "recruitment"}


async def get_system_prompt() -> str:
    return SYSTEM_PROMPT


def get_name() -> str:
    return "Recruitment Advisor"