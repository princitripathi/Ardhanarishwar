from typing import Dict

from app.services.llm import generate_response

SYSTEM_PROMPT = """You are the Career Advisor agent for Ardhanarishwar AI Assistant.

Your purpose is to help users with career-related questions including:
- Career planning and career paths
- Professional guidance and job-search guidance
- Career decisions and professional development

Provide clear, actionable career advice. Focus on practical steps, market trends, and skill recommendations. Never pretend to have access to live job listings or databases. Base your advice on general knowledge and clearly indicate when you're providing general guidance rather than specific data."""


async def get_response(message: str, conversation_history: str = None) -> Dict[str, str]:
    prompt = f"Recent conversation:\n{conversation_history}\n\nCurrent message: {message}" if conversation_history else message
    response = await generate_response(prompt, system_prompt=SYSTEM_PROMPT)
    return {"response": response.response, "intent": "career", "agent": "career"}


async def get_system_prompt() -> str:
    return SYSTEM_PROMPT


def get_name() -> str:
    return "Career Advisor"