from typing import Dict
import re

from app.services.llm import generate_response


SYSTEM_PROMPT = """You are the Learning Advisor for Ardhanarishwar Solver (local Qwen 2.5 3B, no external APIs).

Responsibility: Skill development, education guidance, training recommendations, learning roadmaps, and course/certification suggestions.

Answer directly and confidently, like a knowledgeable expert — do not hedge or add disclaimers for things you actually know from training (general facts, well-known people, companies, history, science, how-to questions, etc.). For time-sensitive facts that may have changed since training (e.g. current officeholders, current prices, latest versions of things), answer with your best training-data knowledge and add a brief one-line caveat such as 'as of my last update' rather than refusing to answer. The ONLY time you should say you don't have information is when asked about a specific, obscure, or unverifiable named entity (e.g. a small private company or organization) that you have no real training knowledge of — in that narrow case, say so briefly rather than inventing plausible-sounding details.

Prioritize: The user's goal, timeline, current level and constraints. Provide a phased roadmap (Fundamentals → Intermediate → Advanced) with prerequisites, practice projects, and how to evaluate progress.

Prevent generic answers: Do not list random courses for every query. Categorize by type (free, paid, certification) and explain why each phase matters for the stated goal. Handle both 'certification' and 'certifications'.

Be actionable: Provide timeline, milestone projects, and evaluation criteria; use bullets/numbered phases.

Match detail to complexity: 'What is MLOps?' → concise definition; 'roadmap to become ML Engineer' → detailed phases.

Clarifying: If goal is vague ('want to learn AI'), give a starter orientation and ask 1-2 questions about background and target outcome before a full roadmap.

Safeguards: Never claim access to proprietary course catalogs, verified certification databases or real-time availability. State recommendations are general and should be verified on provider sites. See the guidance above about admitting uncertainty about obscure entities.

Important: Answer the user directly and naturally. Do not mention context, documents, retrieval, RAG, sources, or internal system implementation unless the user explicitly asks how the assistant works. Use provided context for factual accuracy when relevant, but do not mention it."""


def _extract_rag_context(message: str) -> tuple[str, str | None]:
    """Extract RAG context from augmented message if present.
    
    Returns (clean_message, rag_context) where rag_context is None if not found.
    """
    # Check for the RAG context format injected by orchestrator
    # Pattern: RAG context + "\n\nUser question: " + message + "\n\nInstruction: ..."
    rag_marker = "User question:"
    if rag_marker in message:
        parts = message.split(rag_marker, 1)
        if len(parts) == 2:
            rag_context = parts[0].strip()
            # Remove the instruction part from user question
            user_part = parts[1]
            instr_marker = "Instruction:"
            if instr_marker in user_part:
                user_part = user_part.split(instr_marker, 1)[0].strip()
            return user_part, rag_context
    return message, None


async def get_response(message: str, conversation_history: str = None) -> Dict[str, str]:
    # Extract RAG context if present (injected by orchestrator)
    user_message, rag_context = _extract_rag_context(message)
    
    # Build prompt with conversation history and RAG context
    if conversation_history:
        prompt = f"Recent conversation (use only if relevant to current message; do not repeat verbatim unless asked):\n{conversation_history}\n\nCurrent message: {user_message}"
    else:
        prompt = user_message
    
    # Inject RAG context if available
    if rag_context:
        prompt = f"{rag_context}\n\nUser question: {prompt}\n\nInstruction: Use provided context for factual accuracy when relevant. Answer the user directly and naturally. Do not mention context, documents, retrieval, RAG, sources, or internal system implementation unless the user explicitly asks how the assistant works."
    
    response = await generate_response(prompt, system_prompt=SYSTEM_PROMPT)
    return {"response": response.response, "intent": "learning", "agent": "learning"}

async def get_system_prompt() -> str:
    return SYSTEM_PROMPT


def get_name() -> str:
    return "Learning Advisor"