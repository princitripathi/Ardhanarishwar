from typing import Dict

from app.services.llm import generate_response

SYSTEM_PROMPT = """You are the Learning Agent for Ardhanarishwar AI Assistant.

Your purpose is to help users with skill development and education including:
- Skill development paths
- Education guidance
- Training recommendations
- Learning roadmaps
- Course and skill recommendations

Provide structured learning advice and roadmap suggestions. Never claim access to proprietary course catalogs or certification databases. Base your recommendations on widely known learning resources and general industry knowledge."""


async def get_response(message: str, conversation_history: str = None) -> Dict[str, str]:
    prompt = f"Recent conversation:\n{conversation_history}\n\nCurrent message: {message}" if conversation_history else message
    response = await generate_response(prompt, system_prompt=SYSTEM_PROMPT)
    return {"response": response.response, "intent": "learning", "agent": "learning"}


async def get_system_prompt() -> str:
    return SYSTEM_PROMPT


def get_name() -> str:
    return "Learning Advisor"