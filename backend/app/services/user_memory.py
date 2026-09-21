import sqlite3
import os
import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Bounded, structured, non-sensitive user profile memory
# Clearly separated from short-term conversation_history

# DB path logic similar to interview service — prefer project root data/, fallback backend/data
_base_dir = os.path.dirname(__file__)  # backend/app/services
_project_root_data = os.path.join(_base_dir, "..", "..", "..", "data", "user_memory.db")
_backend_data = os.path.join(_base_dir, "..", "data", "user_memory.db")

# Prefer project root if it exists or can be created, otherwise backend/data
try:
    if os.path.exists(os.path.dirname(_project_root_data)) or not os.path.exists(os.path.dirname(_backend_data)):
        # Ensure directory exists
        os.makedirs(os.path.dirname(_project_root_data), exist_ok=True)
        DB_PATH = _project_root_data
        # Also ensure backend/data exists as fallback mirror? keep single source
    else:
        os.makedirs(os.path.dirname(_backend_data), exist_ok=True)
        DB_PATH = _backend_data
except Exception:
    # Fallback to backend/data
    os.makedirs(os.path.dirname(_backend_data), exist_ok=True)
    DB_PATH = _backend_data

# If both exist, prefer project root data
if os.path.exists(_backend_data) and not os.path.exists(DB_PATH):
    DB_PATH = _backend_data
if os.path.exists(_project_root_data):
    DB_PATH = _project_root_data
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
else:
    # Ensure chosen path dir exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

DEFAULT_USER_ID = "default_user"

# Bounded limits
MAX_NAME_LEN = 50
MAX_GOAL_LEN = 120
MAX_ROLE_LEN = 120
MAX_SKILLS_COUNT = 10
MAX_SKILL_LEN = 30
MAX_INTERESTS_COUNT = 10
MAX_INTEREST_LEN = 50
MAX_PREF_LEN = 200

SENSITIVE_KEYWORDS = [
    "password", "passwd", "secret", "api key", "apikey", "ssn",
    "social security", "credit card", "bank account", "cvv", "pin",
    "private key", "token", "credential", "auth key"
]

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_memory (
            user_id TEXT PRIMARY KEY,
            preferred_name TEXT,
            career_goal TEXT,
            target_role TEXT,
            known_skills TEXT,
            learning_interests TEXT,
            professional_preferences TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

def _row_to_profile(row) -> Optional[Dict]:
    if row is None:
        return None
    d = dict(row)
    # Parse JSON lists
    try:
        d["known_skills"] = json.loads(d["known_skills"]) if d["known_skills"] else []
    except Exception:
        d["known_skills"] = []
    try:
        d["learning_interests"] = json.loads(d["learning_interests"]) if d["learning_interests"] else []
    except Exception:
        d["learning_interests"] = []
    return d

def get_profile(user_id: str = DEFAULT_USER_ID) -> Optional[Dict]:
    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        user_id = DEFAULT_USER_ID
    user_id = user_id.strip()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_memory WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_profile(row)

def list_profiles() -> List[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_memory")
    rows = cur.fetchall()
    conn.close()
    return [_row_to_profile(r) for r in rows]

def _sanitize_text(text: str, max_len: int) -> str:
    if not text or not isinstance(text, str):
        return ""
    t = text.strip()
    # Remove trailing punctuation that is likely sentence terminator not part of value
    t = t.rstrip(" .;:")
    if len(t) > max_len:
        t = t[:max_len].strip()
    return t

def _sanitize_list(items: List[str], max_count: int, max_item_len: int) -> List[str]:
    if not items or not isinstance(items, list):
        return []
    cleaned = []
    seen = set()
    for it in items:
        if not isinstance(it, str):
            continue
        t = it.strip().strip(" .;:,")
        if not t:
            continue
        # Filter sensitive?
        low = t.lower()
        if any(k in low for k in SENSITIVE_KEYWORDS):
            continue
        if len(t) > max_item_len:
            t = t[:max_item_len].strip()
        # Deduplicate case-insensitive
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(t)
        if len(cleaned) >= max_count:
            break
    return cleaned

def _split_skills_like(text: str) -> List[str]:
    # Split by commas, and, &, /, +
    parts = re.split(r"\s*(?:,| and | & | \+ |/)\s*", text, flags=re.IGNORECASE)
    # Further clean each
    results = []
    for p in parts:
        p = p.strip(" .;:")
        if not p:
            continue
        # Remove leading "and " if any
        p = re.sub(r"^and\s+", "", p, flags=re.IGNORECASE).strip()
        if p:
            results.append(p)
    return results

def contains_sensitive_info(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    low = text.lower()
    for kw in SENSITIVE_KEYWORDS:
        if kw in low:
            return True
    # Also detect credit card like pattern 4 groups of 4 digits
    if re.search(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b", text):
        return True
    return False

def extract_memory_updates(message: str) -> Dict:
    """Controlled mechanism to decide what is worth remembering.

    Returns dict with only useful non-sensitive fields if explicitly provided.
    Empty dict means nothing to store (irrelevant or not explicit).
    """
    if not message or not isinstance(message, str) or not message.strip():
        return {}
    if contains_sensitive_info(message):
        return {}

    msg = message.strip()
    low = msg.lower()
    updates: Dict = {}

    # Preferred name: explicit only
    name_patterns = [
        r"\bmy name is\s+([A-Za-z][A-Za-z\s\-\.']{1,48})",
        r"\bcall me\s+([A-Za-z][A-Za-z\s\-\.']{1,48})",
        r"\byou can call me\s+([A-Za-z][A-Za-z\s\-\.']{1,48})",
    ]
    for pat in name_patterns:
        m = re.search(pat, low)
        if m:
            # Extract from original to preserve case, find same span in original
            # Use case-insensitive match but capture from original via same pattern case-insensitive
            orig_m = re.search(pat, msg, flags=re.IGNORECASE)
            if orig_m:
                raw = orig_m.group(1).strip(" .;:,!")
                # Filter out common false positives
                if raw.lower() in ["a", "an", "the", "it", "this", "that"] or len(raw.split()) > 4:
                    # Allow up to 4 words for name, but not generic
                    pass
                else:
                    # Ensure name is not a sentence fragment like "looking for"
                    if "looking" not in raw.lower() and "become" not in raw.lower() and "want" not in raw.lower():
                        updates["preferred_name"] = _sanitize_text(raw, MAX_NAME_LEN)
                        break

    # Career goal
    career_patterns = [
        r"\bi want to become a[n]?\s+([^.!?\n]{3,80})",
        r"\bmy career goal is\s+([^.!?\n]{3,80})",
        r"\baim to become a[n]?\s+([^.!?\n]{3,80})",
        r"\bi want to be a[n]?\s+([^.!?\n]{3,80})",
        r"\bcareer goal\s*[:\-]?\s*([^.!?\n]{3,80})",
    ]
    for pat in career_patterns:
        m = re.search(pat, msg, flags=re.IGNORECASE)
        if m:
            raw = m.group(1).strip(" .;:,!")
            # Filter out if too generic like "a good person"
            if len(raw) >= 3:
                updates["career_goal"] = _sanitize_text(raw, MAX_GOAL_LEN)
                # Also set target_role if it looks like a role (contains developer/engineer/scientist/etc)
                updates["target_role"] = _sanitize_text(raw, MAX_ROLE_LEN)
                break

    # Target role explicit separate (if not already set from career)
    if "target_role" not in updates:
        role_patterns = [
            r"\btarget role is\s+([^.!?\n]{3,80})",
            r"\bapplying for\s+([^.!?\n]{3,80})",
            r"\blooking for a\s+([^.!?\n]{3,80})\s+role",
            r"\bmy target role[:\-]?\s*([^.!?\n]{3,80})",
        ]
        for pat in role_patterns:
            m = re.search(pat, msg, flags=re.IGNORECASE)
            if m:
                raw = m.group(1).strip(" .;:,!")
                if len(raw) >= 3:
                    updates["target_role"] = _sanitize_text(raw, MAX_ROLE_LEN)
                    break

    # Known skills
    skill_patterns = [
        r"\bi know\s+([^.!?\n]{3,80})",
        r"\bmy skills are\s+([^.!?\n]{3,80})",
        r"\bi have experience in\s+([^.!?\n]{3,80})",
        r"\bskilled in\s+([^.!?\n]{3,80})",
        r"\bproficient in\s+([^.!?\n]{3,80})",
        r"\bmy skills\s*[:\-]?\s*([^.!?\n]{3,80})",
    ]
    for pat in skill_patterns:
        m = re.search(pat, msg, flags=re.IGNORECASE)
        if m:
            raw = m.group(1).strip(" .;:,!")
            split = _split_skills_like(raw)
            cleaned = _sanitize_list(split, MAX_SKILLS_COUNT, MAX_SKILL_LEN)
            if cleaned:
                updates["known_skills"] = cleaned
                break

    # Learning interests
    learn_patterns = [
        r"\bi want to learn\s+([^.!?\n]{3,80})",
        r"\binterested in learning\s+([^.!?\n]{3,80})",
        r"\blearning interests?\s*[:\-]?\s*([^.!?\n]{3,80})",
        r"\bwant to study\s+([^.!?\n]{3,80})",
        r"\bkeen to learn\s+([^.!?\n]{3,80})",
    ]
    for pat in learn_patterns:
        m = re.search(pat, msg, flags=re.IGNORECASE)
        if m:
            raw = m.group(1).strip(" .;:,!")
            split = _split_skills_like(raw)
            cleaned = _sanitize_list(split, MAX_INTERESTS_COUNT, MAX_INTEREST_LEN)
            if cleaned:
                updates["learning_interests"] = cleaned
                break
        # Also handle "I want to learn X and Y" where split above handles

    # Professional preferences
    pref_patterns = [
        r"\bi prefer\s+([^.!?\n]{3,80})",
        r"\bmy preference is\s+([^.!?\n]{3,80})",
        r"\bprefer\s+([^.!?\n]{3,80})\s+work",
        r"\blooking for\s+([^.!?\n]{3,80})\s+environment",
    ]
    for pat in pref_patterns:
        m = re.search(pat, msg, flags=re.IGNORECASE)
        if m:
            raw = m.group(1).strip(" .;:,!")
            # Filter out irrelevant like "to learn"
            if "to learn" in raw.lower() or "to become" in raw.lower():
                continue
            if len(raw) >= 3 and not contains_sensitive_info(raw):
                updates["professional_preferences"] = _sanitize_text(raw, MAX_PREF_LEN)
                break

    # Final filtering: remove empty or sensitive
    final = {}
    for k, v in updates.items():
        if isinstance(v, str) and v and not contains_sensitive_info(v):
            final[k] = v
        elif isinstance(v, list) and v:
            # already filtered
            final[k] = v
    return final

def upsert_profile(user_id: str, updates: Dict) -> Optional[Dict]:
    """Create or update profile with bounded, structured updates.

    Only allowed keys are stored; others ignored.
    """
    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        user_id = DEFAULT_USER_ID
    user_id = user_id.strip()
    if not updates or not isinstance(updates, dict):
        return get_profile(user_id)

    allowed_keys = {"preferred_name", "career_goal", "target_role", "known_skills", "learning_interests", "professional_preferences"}
    # Filter to allowed
    filtered: Dict = {}
    for k, v in updates.items():
        if k not in allowed_keys:
            continue
        if k in ("known_skills", "learning_interests"):
            if isinstance(v, str):
                # Split string into list
                v = _split_skills_like(v)
            if isinstance(v, list):
                max_c = MAX_SKILLS_COUNT if k == "known_skills" else MAX_INTERESTS_COUNT
                max_l = MAX_SKILL_LEN if k == "known_skills" else MAX_INTEREST_LEN
                filtered[k] = _sanitize_list(v, max_c, max_l)
            else:
                continue
        elif k in ("preferred_name", "career_goal", "target_role", "professional_preferences"):
            if not isinstance(v, str) or not v.strip():
                continue
            if contains_sensitive_info(v):
                continue
            max_l = MAX_NAME_LEN if k == "preferred_name" else (MAX_GOAL_LEN if k == "career_goal" else (MAX_ROLE_LEN if k == "target_role" else MAX_PREF_LEN))
            filtered[k] = _sanitize_text(v, max_l)
        else:
            filtered[k] = v

    if not filtered:
        return get_profile(user_id)

    conn = get_connection()
    cur = conn.cursor()
    # Check existing
    cur.execute("SELECT * FROM user_memory WHERE user_id = ?", (user_id,))
    existing = cur.fetchone()
    now = _now_iso()

    if existing:
        # Merge: for lists, extend/merge? For prototype, replace with new merged bounded list (deduplicate)
        old = _row_to_profile(existing)
        merged = {}
        for key in allowed_keys:
            if key in filtered:
                if key in ("known_skills", "learning_interests"):
                    # Merge old + new, deduplicate
                    old_list = old.get(key) or []
                    new_list = filtered[key]
                    combined = old_list + new_list
                    # dedup case-insensitive preserve order
                    seen = set()
                    deduped = []
                    for item in combined:
                        lk = item.lower()
                        if lk not in seen:
                            seen.add(lk)
                            deduped.append(item)
                    max_c = MAX_SKILLS_COUNT if key == "known_skills" else MAX_INTERESTS_COUNT
                    merged[key] = deduped[:max_c]
                else:
                    merged[key] = filtered[key]
            else:
                # keep old if not updating
                merged[key] = old.get(key)

        # Prepare update
        cur.execute("""
            UPDATE user_memory SET
                preferred_name = ?,
                career_goal = ?,
                target_role = ?,
                known_skills = ?,
                learning_interests = ?,
                professional_preferences = ?,
                updated_at = ?
            WHERE user_id = ?
        """, (
            merged.get("preferred_name"),
            merged.get("career_goal"),
            merged.get("target_role"),
            json.dumps(merged.get("known_skills") or []),
            json.dumps(merged.get("learning_interests") or []),
            merged.get("professional_preferences"),
            now,
            user_id
        ))
        conn.commit()
        conn.close()
        _invalidate_memory_cache(user_id)
        return get_profile(user_id)
    else:
        # Insert new
        cur.execute("""
            INSERT INTO user_memory
            (user_id, preferred_name, career_goal, target_role, known_skills, learning_interests, professional_preferences, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            filtered.get("preferred_name"),
            filtered.get("career_goal"),
            filtered.get("target_role"),
            json.dumps(filtered.get("known_skills") or []),
            json.dumps(filtered.get("learning_interests") or []),
            filtered.get("professional_preferences"),
            now,
            now
        ))
        conn.commit()
        conn.close()
        _invalidate_memory_cache(user_id)
        return get_profile(user_id)

def delete_profile(user_id: str = DEFAULT_USER_ID) -> bool:
    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        user_id = DEFAULT_USER_ID
    user_id = user_id.strip()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_memory WHERE user_id = ?", (user_id,))
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    _invalidate_memory_cache(user_id)
    return changed

def clear_all() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_memory")
    conn.commit()
    conn.close()
    clear_memory_cache()

# Phase 8: cache for build_memory_context to avoid repeated SQLite reads per request
_memory_context_cache: Dict[str, tuple] = {}  # user_id -> (timestamp, context_str, updated_at)
_MEMORY_CACHE_TTL = 30.0

def _invalidate_memory_cache(user_id: str) -> None:
    _memory_context_cache.pop(user_id, None)
    _memory_context_cache.pop(DEFAULT_USER_ID, None)

def build_memory_context(user_id: str = DEFAULT_USER_ID) -> str:
    """Build concise memory string for prompt injection.

    Only relevant non-empty fields are included.
    """
    import time as _time
    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        user_id = DEFAULT_USER_ID
    user_id = user_id.strip()
    now = _time.monotonic()
    cached = _memory_context_cache.get(user_id)
    if cached is not None:
        ts, ctx, upd = cached
        if now - ts < _MEMORY_CACHE_TTL:
            # Validate that profile hasn't changed since cache (check updated_at)
            # Quick path: if cache exists and no DB write since, reuse
            return ctx
    profile = get_profile(user_id)
    if not profile:
        _memory_context_cache[user_id] = (now, "", "")
        return ""
    parts = []
    if profile.get("preferred_name"):
        parts.append(f"Preferred name: {profile['preferred_name']}")
    if profile.get("career_goal"):
        parts.append(f"Career goal: {profile['career_goal']}")
    if profile.get("target_role"):
        # Avoid duplicating if same as career_goal
        if profile.get("target_role") != profile.get("career_goal"):
            parts.append(f"Target role: {profile['target_role']}")
    if profile.get("known_skills"):
        skills = ", ".join(profile["known_skills"])
        parts.append(f"Known skills: {skills}")
    if profile.get("learning_interests"):
        interests = ", ".join(profile["learning_interests"])
        parts.append(f"Learning interests: {interests}")
    if profile.get("professional_preferences"):
        parts.append(f"Professional preferences: {profile['professional_preferences']}")
    if not parts:
        _memory_context_cache[user_id] = (now, "", profile.get("updated_at", ""))
        return ""
    # Format as bullet list for LLM
    header = "User Profile (long-term memory - use when relevant to the question):"
    body = "\n".join(f"- {p}" for p in parts)
    footer = "(Use this profile to personalize the answer when relevant; do not mention memory unless useful.)"
    ctx = f"{header}\n{body}\n{footer}"
    _memory_context_cache[user_id] = (now, ctx, profile.get("updated_at", ""))
    return ctx


def clear_memory_cache() -> None:
    _memory_context_cache.clear()

def maybe_update_from_message(user_id: str, message: str) -> Optional[Dict]:
    """Controlled update: only if extract finds explicit worth-remembering info.

    Returns updated profile or None if nothing to store.
    """
    updates = extract_memory_updates(message)
    if not updates:
        return None
    return upsert_profile(user_id, updates)
