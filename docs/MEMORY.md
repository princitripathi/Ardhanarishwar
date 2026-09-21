# User Memory — Phase 5 Controlled Long-Term Profile

## Goal
Remember useful non-sensitive user preferences across conversations without storing everything.

## Model
Structured, bounded profile stored per `user_id` in SQLite (`data/user_memory.db` with fallback `backend/data/user_memory.db`), separate from short-term `conversation_memory` (in-memory, per `conversation_id`).

| Field | Source pattern example | Bounded |
|-------|------------------------|---------|
| `preferred_name` | "My name is Priya", "Call me Amit" | 50 chars |
| `career_goal` | "I want to become a Generative AI Developer", "My career goal is ..." | 120 chars |
| `target_role` | "Target role is ML Engineer", "Applying for ..." | 120 chars |
| `known_skills` | "I know Python, Java", "My skills are ..." | 10 × 30 chars |
| `learning_interests` | "I want to learn MLOps", "Interested in learning ..." | 10 × 50 chars |
| `professional_preferences` | "I prefer remote work", "My preference is ..." | 200 chars |

## Controlled Extraction
`app/services/user_memory.py:extract_memory_updates`:
- Only returns dict when explicit regex matches.
- Returns `{}` for irrelevant messages ("What should I learn next?", "What's the weather?", "Tell me a joke").
- Blocks sensitive: `SENSITIVE_KEYWORDS` (password, api key, credit card, ssn, etc.) + regex for card numbers.
- Sanitize: trim, strip punctuation, truncate to limits, dedup lists case-insensitively.

`maybe_update_from_message(user_id, message)` calls `extract → upsert` only if non-empty.

## Persistence
- `init_db()` creates `user_memory` table with `user_id` PK, `known_skills`/`learning_interests` as JSON text.
- File survives restart (tested by querying file directly after insert). Not claimed persistent until file exists — verified in `test_persistence_across_restart`.
- Uses existing DB pattern (like `interview/service.py`), no new infrastructure.

## Bounded & Editable
- Lists merged deduplicated, capped to 10.
- String fields truncated to max lengths.
- `upsert_profile` merges lists, overwrites scalars.
- `delete_profile`, `clear_all`, `list_profiles` provide deletion.
- `build_memory_context` only emits non-empty fields as bullet list.

## Integration with Agents
`app/services/orchestrator.py`:
- `route_message(message, conversation_id, user_id)` and `stream_message(..., user_id)` resolve `uid = _get_user_id(conversation_id, user_id)` → default `default_user`.
- `_maybe_store_memory(uid, message)` before handling.
- `_get_memory_context(uid)` → injected via `_augment_with_memory` before RAG/history:
  ```
  User Profile (long-term memory - use when relevant):
  - Career goal: Generative AI Developer
  - Known skills: Python
  (Use this profile to personalize…)

  [Recent conversation ...]

  User question: What should I learn next?
  ```
- Clearly separated: short-term dict vs SQLite profile.

`app/main.py:ChatRequest` adds optional `user_id`; `app/services/memory_routes.py` exposes CRUD:
- `POST /api/memory` {user_id, preferred_name, career_goal, ...}
- `GET /api/memory/{user_id}` and `GET /api/memory?user_id=`
- `PUT /api/memory/{user_id}`
- `DELETE /api/memory/{user_id}`
- `GET /api/memory/context/{user_id}`
- `POST /api/memory/clear` (or with user_id)

## Example
```
User (convA, userA): "I want to become a Generative AI Developer." → stored career_goal
User (convB, same userA): "What should I learn next?" → prompt includes Career goal: Generative AI Developer
```

## Tests
`backend/tests/test_memory.py` (20):
- create (explicit, name, skills, interests)
- update (career goal, skills merge, bounded)
- retrieve (exists, nonexistent, list)
- irrelevant not stored (also via orchestrator)
- sensitive blocked
- using memory in prompts (via mocked learning_agent)
- using across conversations (example scenario)
- separated from short-term
- clear (single, all)
- API CRUD
- bounded fields
- editable/deletable
- persistence across restart (file query)
- default_user persists

Also `tests/conftest.py` ensures isolation by clearing `user_memory` before each test.

Run:
```bash
cd backend
python -m pytest tests/test_memory.py -v
python -m pytest tests/ -v
```

## Limitations (Prototype)
- Single SQLite file, no migration/versioning.
- `user_id` is client-provided; no auth.
- Pattern-based extraction is heuristic, not NER.

## Next Steps if Scaling
- Replace regex with LLM-assisted extraction with validation.
- Add per-field consent UI.
- Move to PostgreSQL + encryption at rest.
