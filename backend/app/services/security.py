"""
Basic security hardening for Ardhanarishwar Solver prototype.
Internal/company use — no external auth, but protect against obvious abuses.
No complex infra (no Redis, no JWT) — in-memory lightweight checks.
"""
import re
import time
import logging
from typing import Dict, Tuple
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

# ---------- Bounded input limits ----------
MAX_MESSAGE_LEN = 4000
MAX_CONVERSATION_ID_LEN = 64
MAX_USER_ID_LEN = 64
MAX_TITLE_LEN = 100
MAX_SOURCE_LEN = 200
MAX_DOC_TEXT_LEN = 50000  # ~12k tokens, prevents DoS
MAX_QUERY_LEN = 2000
MAX_DOCS_TOTAL = 100
MAX_DOC_ID_LEN = 64
MAX_SKILLS_TEXT_LEN = 200  # for memory etc

ALLOWED_DOC_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
ALLOWED_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

SENSITIVE_REDACT_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9\-_\.]+", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"), "[REDACTED_CARD]"),
    (re.compile(r"password\s*[:=]\s*\S+", re.IGNORECASE), "password=[REDACTED]"),
    (re.compile(r"api[_-]?key\s*[:=]\s*\S+", re.IGNORECASE), "api_key=[REDACTED]"),
]

# Prompt injection markers: instruct model to ignore retrieved doc instructions
INJECTION_MARKERS = [
    r"ignore\s+previous\s+instructions",
    r"ignore\s+above\s+instructions",
    r"disregard\s+.*instructions",
    r"system\s*:\s*",
    r"assistant\s*:\s*",
    r"user\s*:\s*",
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"```\s*system",
    r"you\s+are\s+now\s+",
    r"reveal\s+system\s+prompt",
    r"do\s+not\s+follow",
]

INJECTION_RE = re.compile("|".join(INJECTION_MARKERS), re.IGNORECASE)

# ---------- Helpers ----------

def redact_sensitive(text: str) -> str:
    if not text or not isinstance(text, str):
        return text
    redacted = text
    for pat, repl in SENSITIVE_REDACT_PATTERNS:
        redacted = pat.sub(repl, redacted)
    return redacted

def is_valid_id(value: str, max_len: int = 64) -> bool:
    if not value or not isinstance(value, str):
        return False
    v = value.strip()
    if not v or len(v) > max_len:
        return False
    # allow uuid form with dashes, alphanumeric
    if not ALLOWED_ID_RE.match(v):
        return False
    if ".." in v or "/" in v or "\\" in v:
        return False
    return True

def sanitize_for_log(text: str, max_len: int = 200) -> str:
    if not text:
        return ""
    # redacted + truncated + single line
    redacted = redact_sensitive(text)
    single = redacted.replace("\n", " ").replace("\r", " ")
    if len(single) > max_len:
        return single[:max_len] + "…"
    return single

def sanitize_retrieved_text(text: str, max_len: int = 2000) -> str:
    """Treat retrieved docs as untrusted. Escape instruction-like content and bound length."""
    if not text or not isinstance(text, str):
        return ""
    # truncate
    t = text.strip()
    if len(t) > max_len:
        t = t[:max_len].rsplit(" ", 1)[0] + "…"
    # Escape common prompt injection tokens
    # Replace markers with bracketed version so LLM sees them as data, not instruction
    # e.g., "ignore previous instructions" -> "[filtered instruction]"
    if INJECTION_RE.search(t):
        # Replace each match with neutral placeholder, log occurrence
        t = INJECTION_RE.sub("[untrusted content]", t)
    # Wrap to make clear it's data, not instruction — done by caller format_context
    # Also neutralize triple backticks that could break markdown
    t = t.replace("```", "` ` `")
    # Neutralize <script etc?
    t = re.sub(r"<script", "[blocked script]", t, flags=re.IGNORECASE)
    return t

def validate_message(text: str) -> str:
    if text is None or not isinstance(text, str):
        raise ValueError("Message must be a string")
    stripped = text.strip()
    if not stripped:
        raise ValueError("Message cannot be empty")
    if len(stripped) > MAX_MESSAGE_LEN:
        raise ValueError(f"Message too long (max {MAX_MESSAGE_LEN} chars)")
    # Optional: detect obvious injection in user message? Not blocking, but log
    if len(stripped) < 1:
        raise ValueError("Message too short")
    return stripped

def validate_doc_text(text: str) -> str:
    if text is None or not isinstance(text, str):
        raise ValueError("Document text must be a string")
    stripped = text.strip()
    if not stripped:
        raise ValueError("Document text cannot be empty")
    if len(stripped) < 10:
        raise ValueError("Document text too short (minimum 10 chars)")
    if len(stripped) > MAX_DOC_TEXT_LEN:
        raise ValueError(f"Document too large (max {MAX_DOC_TEXT_LEN} chars)")
    return stripped

def validate_title(title) -> str:
    if title is None:
        return None
    if not isinstance(title, str):
        raise ValueError("title must be a string")
    t = title.strip()
    if not t:
        return None
    if len(t) > MAX_TITLE_LEN:
        raise ValueError(f"title too long (max {MAX_TITLE_LEN})")
    if ".." in t or "/" in t or "\\" in t:
        raise ValueError("title contains invalid path characters")
    return t

def validate_source(source) -> str:
    if source is None:
        return None
    if not isinstance(source, str):
        raise ValueError("source must be a string")
    s = source.strip()
    if not s:
        return None
    if len(s) > MAX_SOURCE_LEN:
        raise ValueError(f"source too long (max {MAX_SOURCE_LEN})")
    if ".." in s or "/" in s or "\\" in s:
        # allow slashes? For safety, forbid traversal
        if ".." in s:
            raise ValueError("source contains path traversal")
    return s

def validate_doc_id(doc_id) -> str:
    if doc_id is None:
        return None
    if not isinstance(doc_id, str):
        raise ValueError("doc_id must be a string")
    d = doc_id.strip()
    if not d:
        return None
    if not is_valid_id(d, MAX_DOC_ID_LEN):
        raise ValueError("doc_id contains invalid characters or too long (allowed A-Za-z0-9._- max 64)")
    return d

# ---------- Simple in-memory rate limiting ----------
# For prototype: 30 requests per minute per IP for chat, 20 for ingest
# Uses sliding window via deque of timestamps

class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window = window_seconds
        self.buckets: Dict[str, deque] = defaultdict(deque)
    
    def is_allowed(self, key: str) -> Tuple[bool, int]:
        now = time.monotonic()
        dq = self.buckets[key]
        # evict old
        while dq and dq[0] <= now - self.window:
            dq.popleft()
        if len(dq) >= self.max_requests:
            # retry after = oldest + window - now
            retry_after = int(dq[0] + self.window - now) + 1
            return False, retry_after
        dq.append(now)
        return True, 0
    
    def clear(self):
        self.buckets.clear()

# Global limiters
chat_limiter = RateLimiter(max_requests=30, window_seconds=60)
ingest_limiter = RateLimiter(max_requests=20, window_seconds=60)
interview_limiter = RateLimiter(max_requests=20, window_seconds=60)

def get_client_key(request) -> str:
    # Prefer X-Forwarded-For if behind proxy (first entry), else client host
    try:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
    except Exception:
        pass
    return "unknown"

def redact_for_log_kwargs(**kwargs) -> Dict:
    out = {}
    for k, v in kwargs.items():
        if isinstance(v, str):
            out[k] = sanitize_for_log(v)
        else:
            out[k] = v
    return out

# ---------- CORS helper ----------
def get_allowed_origins():
    import os
    env_origins = os.getenv("FRONTEND_URL", "http://localhost:5173")
    # support comma-separated list
    parts = [p.strip() for p in env_origins.split(",") if p.strip()]
    # always allow localhost dev if not explicitly listed? keep strict: only env
    # If no env, default to localhost:5173
    if not parts:
        return ["http://localhost:5173"]
    return parts
