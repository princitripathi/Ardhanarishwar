import uuid
from typing import Dict, List, Optional

# In-memory store: conversation_id -> list of {role, content}
# Bounded to 20 messages (10 turns)
MAX_TURNS = 10
MAX_MESSAGES = MAX_TURNS * 2  # user+assistant per turn

_conversations: Dict[str, List[Dict[str, str]]] = {}


def get_conversation_id(provided: Optional[str]) -> str:
    if provided and isinstance(provided, str) and provided.strip():
        return provided.strip()
    return str(uuid.uuid4())


def get_history(conversation_id: str) -> List[Dict[str, str]]:
    return list(_conversations.get(conversation_id, []))


def add_message(conversation_id: str, role: str, content: str) -> None:
    if not content or not content.strip():
        return
    if role not in ("user", "assistant"):
        return
    hist = _conversations.get(conversation_id)
    if hist is None:
        hist = []
        _conversations[conversation_id] = hist
    hist.append({"role": role, "content": content.strip()})
    # bound to MAX_MESSAGES most recent
    if len(hist) > MAX_MESSAGES:
        # keep last MAX_MESSAGES
        _conversations[conversation_id] = hist[-MAX_MESSAGES:]


def build_context(history: List[Dict[str, str]], limit: int = 6) -> str:
    """Build concise recent history string, limited to last `limit` messages."""
    if not history:
        return ""
    recent = history[-limit:]
    lines = []
    for msg in recent:
        role = "User" if msg["role"] == "user" else "Assistant"
        # truncate each message to avoid bloat
        content = msg["content"][:400].strip()
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def clear_conversation(conversation_id: str) -> None:
    _conversations.pop(conversation_id, None)


def clear_all() -> None:
    _conversations.clear()


def conversation_exists(conversation_id: str) -> bool:
    return conversation_id in _conversations

# For testing: expose store size
def _store_size() -> int:
    return len(_conversations)
