from typing import Dict

from app.services.llm import generate_response

SYSTEM_PROMPT = """You are the Business Agent for Ardhanarishwar AI Assistant.

Your purpose is to help users with business-related questions including:
- Business problems and solutions
- Workforce planning
- HR and business assistance
- Business process guidance
- General business queries

Provide clear, practical business advice. Never claim access to proprietary business databases or market analytics. Base your guidance on general business knowledge and clearly indicate when you're providing general recommendations."""


async def get_response(message: str, conversation_history: str = None) -> Dict[str, str]:
    prompt = f"Recent conversation:\n{conversation_history}\n\nCurrent message: {message}" if conversation_history else message
    response = await generate_response(prompt, system_prompt=SYSTEM_PROMPT)
    return {"response": response.response, "intent": "business", "agent": "business"}


async def get_system_prompt() -> str:
    return SYSTEM_PROMPT


def get_name() -> str:
    return "Business Advisor"