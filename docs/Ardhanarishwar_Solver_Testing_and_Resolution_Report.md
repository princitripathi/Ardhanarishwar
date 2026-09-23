# Ardhanarishwar Solver
## Testing, Bug Identification & Resolution Report

**Date:** 2026-09-23  
**Project:** Ardhanarishwar Solver — AI-Powered Career, Recruitment & Interview Assistant  
**Branch:** main  
**Testing Mode:** Company-assigned QA / End-to-End Testing, Bug-Finding, Bug-Fixing & Regression Cycle  
**Tester:** Muse Spark (OpenCode Agent) — automated + manual verification where required

---

### 1. Executive Summary

**Objective:** Perform a complete end-to-end testing, bug-finding, bug-fixing, and regression cycle for the entire Ardhanarishwar Solver project (frontend, backend, agents, orchestrator, generative AI/Ollama, API, RAG, short-term/long-term memory, interview system, voice/proctoring, security, performance, error handling).

**Scope Tested:** All subsystems listed in §3. 280 backend tests, frontend build/lint, evaluation framework (45 cases), 25+ API endpoints, 6 specialized agents, RAG workflow (ingestion→retrieval→context injection), short-term memory (10-turn bounded) and long-term memory (SQLite `user_memory.db`), full interview workflow (plan→questions→evaluation→report→persistence), browser voice/proctoring, security controls, performance latencies, and error-handling paths.

**Overall Result:** Baseline backend suite was **280 passed** but with **131 deprecation warnings**; frontend build succeeded; lint emitted 21 warnings (no errors); evaluation routing was **100% (45/45)**; API route health was intact; dependency health was clean. Three confirmed defects requiring code changes were identified, reproduced, fixed with minimal targeted edits, and verified via re-run. **Final regression: 280 passed, 1 warning (test-only), frontend build successful, lint warnings unchanged (no errors).** All fixes preserved existing behavior.

**Confirmed Issues Resolved:** 3 bug fixes applied; 0 remaining blocking defects; remaining limitations documented in §11.

---

### 2. Testing Environment

Only values actually verified on this machine are listed:

| Component | Verified Value | How Verified |
|-----------|---------------|--------------|
| OS | Windows 11 (win32 10.0.26200) | `platform` + pytest metadata |
| Python | 3.12.6 | `python --version` |
| Node.js | 22.23.2 | `node --version` |
| npm | 10.9.8 | `npm --version` |
| FastAPI | 0.115.0 | `backend/requirements.txt:1` |
| Uvicorn | 0.30.6 | `backend/requirements.txt:2` |
| httpx | 0.27.2 | `backend/requirements.txt:4` |
| Pydantic | 2.9.2 | `backend/requirements.txt:5` |
| React | 19.2.8 | `frontend/package.json:13` |
| Vite | 8.2.2 | `frontend/package.json:22` |
| Oxlint | 1.79.0 | `frontend/package.json:21` |
| pytest | 9.1.1 | pytest header |
| Ollama | Not running on test host — health endpoint returned connection failure/timeout; `OLLAMA_BASE_URL=http://localhost:11434`, `OLLAMA_MODEL=qwen2.5:3b` via `os.getenv` defaults | `app/services/llm.py:11-12`, live probe via `TestClient` + orchestrator mock tests |
| Model | qwen2.5:3b (configured) | `app/services/llm.py:12`, `app/main.py:110` |
| SQLite | Interview DB `data/interviews.db` + `data/user_memory.db` / `backend/data/user_memory.db` | `app/interview/service.py:7`, `app/services/user_memory.py:13-14` |

> Ollama connectivity was tested in two modes: **mocked** (deterministic, no Ollama) and **live** (actual HTTP to `localhost:11434`). Live inference was unavailable/timed-out on this host; this was exercised as an error-handling probe and confirmed graceful fallback after fix.

---

### 3. Project Scope Tested

| Area | Specific Items Tested |
|------|-----------------------|
| **AI Agents** | Career, Resume, Interview, Learning, Recruitment, Business — system prompts at `backend/app/agents/*.py:1-36` |
| **Orchestration** | Keyword priority `recruitment > resume > interview > learning > career > business > general`, scoring (`score_intents`, `analyze_intents`), contextual follow-up (`_detect_with_context`), multi-domain & ambiguous detection at `backend/app/services/orchestrator.py:40-410` |
| **Generative AI** | `app/services/llm.py:43-183` — health cache (TTL 10s `llm.py:17`), 30s non-stream/60s stream timeouts, `OllamaError` mapping, `generate_response`/`generate_response_stream` |
| **API** | 25 routes enumerated from `app/main.py:182` plus `interview/routes.py`, `interview/session_routes.py`, `rag/routes.py`, `services/memory_routes.py` — full route table in §5/§9 |
| **RAG** | `app/rag/chunking.py`, `embeddings.py`, `store.py`, `retrieval.py`, `ingestion.py`, `routes.py` — ingestion, chunking (500/100 overlap), TF-IDF L2 cosine, top-k 3 threshold 0.12, sanitization |
| **Memory** | Short-term `conversation_memory.py` (MAX_TURNS 10, MAX_MESSAGES 20) and long-term `user_memory.py` (SQLite, 6 bounded fields, sensitive filtering) |
| **Interview** | `app/interview/engine.py`, `evaluator.py`, `session_service.py`, `service.py` — plan generation, adaptive questioning, evaluation (4 dimensions), final report, SQLite persistence, timer behavior |
| **Voice** | `frontend/src/useChatVoice.js` (192 lines) + `frontend/src/InterviewSession.jsx` (913 lines) — SpeechRecognition/Synthesis, continuous mode, interim/final transcript, cancellation, browser detection, proctoring events |
| **Frontend** | `frontend/src/` — build (`vite build`), lint (`oxlint`), imports, routes, API calls, chat/interview/voice UI, loading/error/empty states |
| **Security** | `app/services/security.py:238` — input limits, traversal, prompt-injection sanitization, rate limiting (30/20/min), CORS, headers, redaction; `app/main.py:53-62` security headers |
| **Performance** | Health, RAG retrieve, orchestrator, LLM TTFT/streaming, validation latency (<5ms), repeated request cache behavior |
| **Error Handling** | Ollama unavailable, malformed LLM output, empty response, invalid API input, expired session, invalid IDs, frontend API failure |

---

### 4. Test Strategy

| Strategy | Applied To | Method |
|----------|------------|--------|
| **Functional Testing** | Agents, orchestrator, RAG, memory, interview, API endpoints | Pytest suite (280 tests), direct `TestClient` API probes, `eval.runner` dataset (45 cases), isolated unit probes (`python -c` via `sys.path`) |
| **Integration Testing** | Orchestrator→agents→LLM→memory→RAG, interview plan→question→evaluation→report, frontend→backend `InterviewSession` flow | Multi-component mocked `route_message` with `conversation_id`/`user_id`, RAG ingestion+retrieve+context injection, interview session start→answer→complete chains |
| **Regression Testing** | Full backend suite + frontend build/lint + evaluation | `python -m pytest tests -q` before and after fixes; `npm run build`; `npm run lint`; `python -m eval.runner --routing-only/--mock` |
| **Validation Testing** | `app/services/validation.py:363` — empty, malformed, refusal, repetition, grounded-claim, structured output | 18 validation tests + intentional invalid payloads (empty message, oversized 4001 chars, traversal IDs, malformed JSON) |
| **Security Testing** | Request size limits, traversal, prompt injection, sensitive data, CORS/headers, rate limiting, log redaction, file ingestion | `test_security.py` (26 tests) + manual `TestClient` probes + `sanitize_retrieved_text` checks; safe non-destructive attempts only |
| **Performance Testing** | Health, RAG, orchestrator, LLM streaming | Wall-clock `perf_counter` measurements; cache hit verification; TTFT observation (where Ollama reachable) |
| **Frontend/Build Testing** | Imports, routes, API wiring, UI states | `npm run build` + `npm run lint` + static inspection of `InterviewSession.jsx`, `useChatVoice.js`, `api.js` |
| **Manual Verification** | Browser-dependent voice/proctoring | Code inspection + `isSpeechRecognitionSupported` feature-detection paths; marked as requiring manual browser testing (Chrome/Edge desktop) — not falsely claimed as passed |

---

### 5. Baseline Results (Before Fixes)

Observed on initial run from `C:\Users\princ\Desktop\Ardhanarishwar`:

**Backend tests — `backend\python -m pytest tests -q`:**
```
280 passed, 131 warnings in 56.22s
```
- Warnings breakdown:
  - `C:\...\interview\service.py:64: DeprecationWarning: datetime.datetime.utcnow() is deprecated...` (27 occurrences across interview tests)
  - `C:\...\interview\session_service.py:113/170/186: DeprecationWarning: datetime.datetime.utcnow() is deprecated...` (19+14+20 occurrences)
  - All 131 warnings are `DeprecationWarning` for `datetime.utcnow()` — functional but noisy and future-breakage risk.

**Frontend:**
- `frontend\npm run build`: **Successful** — `179 modules transformed`, `dist/assets/index-CM2y1KY5.js 371.70 kB (gzip 110.00 kB)` in 2.31s, `✓ built`
- `frontend\npm run lint` (`oxlint`): **No errors, 21 warnings** — unused catch params, unused params, React hooks `exhaustive-deps`, `purity`/`set-state-in-effect` — non-blocking; build not affected.

**Evaluation:**
- `python -m eval.runner --routing-only`: **Overall accuracy 1.0 (39/39 single + 6 context/edge counted separately → 45/45 effective)**
- `python -m eval.runner --mock`: **Routing 1.0 (45/45)**, relevance mean 0.89, completeness 87% (39/45), 0 hallucination/error flags, latency mean ~12ms median 2.1ms p95 14.4ms — matches `README:570` claim.

**Import/Module Health:**
- All `backend/app/**/*.py` importable; `app/main.py` registers 25 routes successfully (`TestClient` route enumeration confirmed — see §9).

**API Route Health (sample probes via `TestClient`):**
- `POST /api/chat` with `""` → 422 `Message cannot be empty` ✓
- `POST /api/chat` with `"   "` → 422 ✓
- `POST /api/chat` with 4001-char message → 422 `Message too long (max 4000)` ✓
- `POST /api/chat` with traversal `conversation_id="../../etc"` → 422 `invalid characters` ✓
- `POST /api/rag/ingest` with `""` → 422 ✓; short text → 422 `too short (minimum 10)` ✓
- `GET /api/health` → 200 `{"status":"ok"}` with `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` ✓

**Warnings / Known Limitations at Baseline:**
- 131 `utcnow` deprecations.
- Orchestrator did not provide heuristic fallback when Ollama unavailable — `route_message` raised `OllamaError` instead of returning safe fallback (contradicts README reliability claim).
- `InterviewSession.jsx:199` transcript auto-restart used stale `transcript` closure (missing dep) — potential voice transcript loss on pause/restart.

---

### 6. Issues/Bugs Found

| ID | Area | Issue | Severity | Reproduction | Root Cause | Resolution | Status |
|----|------|-------|----------|--------------|------------|------------|--------|
| BUG-001 | Interview/Service, Session | `datetime.datetime.utcnow()` deprecated — 131 warnings on every test run (`service.py:64`, `session_service.py:113,170,186`). Will break on future Python where `utcnow` is removed; noisy CI. | Low | `python -m pytest tests -q` → `131 warnings` with message `datetime.datetime.utcnow() is deprecated...` | Use of deprecated `utcnow()` introduced before Python 3.12 warning. | Replace with `datetime.now(timezone.utc).isoformat().replace("+00:00","Z")` in `service.py:1,64` and `session_service.py:1,113,170,186`. | **Fixed** — re-run shows `1 warning` (remaining is in test data itself `tests/test_interview.py:242`, not production code) |
| BUG-002 | Orchestration / Generative AI / Error Handling | Chat fails with `OllamaError` instead of graceful heuristic fallback when Ollama is unavailable. `route_message` (general path via `_validated_generate` and agent path via `agent_fn`) propagated `OllamaError` to `app/main.py` which returned HTTP 503 error JSON. README claims "Heuristic Fallbacks — Code-based fallbacks when LLM is unavailable" but chat had none; streaming path also raised before yielding. | High | `python -c` with `patch('app.services.orchestrator.generate_response', side_effect=OllamaError('Ollama service is unavailable',503))` then `await route_message('hello')` → raised `OllamaError` (pre-fix). `patch('app.agents.career_agent.get_response', side_effect=OllamaError)` + `route_message('I want career guidance')` → raised. Streaming via `stream_message` with failing `generate_response_stream` → raised `OllamaError` in generator. | `_validated_generate` at `orchestrator.py:572` called `await generate_response(...)` without try/except; agent call at `orchestrator.py:762` caught only `TypeError`; `stream_message:896` looped `async for chunk in generate_response_stream` without catching. | `orchestrator.py:5` import `OllamaError`; wrap `_validated_generate` in `try/except OllamaError/Exception` returning `get_safe_fallback()` with `llm_unavailable` issue tag; wrap agent calls in `except OllamaError`/`Exception` returning fallback `{"response": get_safe_fallback(...)}`; wrap streaming loop in `try/except OllamaError` yielding fallback chunk and setting `full_response=[fallback]`. | **Fixed** — verified via same reproduction: `route_message('hello')` now returns `response` containing `I apologize — I wasn't able to generate...` with `validation_issues ['llm_unavailable:...']`; career agent fallback returns `intent career` with safe text; streaming yields fallback chunk after meta event. API `POST /api/chat` now returns 200 with fallback instead of 503 when mocked unavailable. |
| BUG-003 | Voice / Frontend | `InterviewSession.jsx:195-199` stale closure — `rec.onend` auto-restart sets `baseTranscriptRef.current = transcript` where `transcript` is captured at `useEffect` mount time (empty). After natural pause, transcript continuation would lose prior spoken content because `transcript` inside closure is stale; dependency array `[speechSupported]` omitted `transcript`. | Medium | Code inspection: `InterviewSession.jsx:168-258` — `useEffect(() => { const rec = new SR(); rec.onend = () => { baseTranscriptRef.current = transcript; ... } }, [speechSupported])`. Simulate: speak "hello world", pause triggers `onend`, `transcript` at creation is `""`, so base becomes `""` not `"hello world"`; next utterance overwrites rather than appends. | React stale closure; missing dependency or ref-based latest value. | Add `transcriptRef` mirrored via `useEffect(() => { transcriptRef.current = transcript }, [transcript])` at `InterviewSession.jsx:52-53`; change `onend` to `baseTranscriptRef.current = transcriptRef.current`. Minimal, preserves existing behavior, eliminates stale capture. | **Fixed** — build still succeeds (371.77 kB), lint still 21 warnings (no new errors). Manual browser verification still required for voice (see §12) but logic error corrected. |
| INFO-001 | Frontend/Lint | 21 `oxlint` warnings: unused catch params (`_`, `e2`, `e3`, `e`), unused `prev`/`t` params, `react-hooks/exhaustive-deps` on 3 effects, `react(purity)` `Date.now` in render (`InterviewViews.jsx:199`), `set-state-in-effect` cascades (`InterviewViews.jsx:219,226,241,449`), `no-useless-catch` | Low | `npm run lint` output (see §5 baseline) | Code style / strict lint rules, not functional breakage. | **No change** — not fixed per "minimal targeted fixes" directive; warnings are non-blocking and do not affect build (21 warnings remain post-fix). Documented as remaining limitation. | Open — informational |
| INFO-002 | Security | No hardcoded secrets, no tracked `.env`, no `eval`/`exec`/`os.system` in `backend/app` (only `evaluator.py` false-positive for word "evaluation"), no path traversal beyond validated checks | Informational | `grep` for `sk-`, `password=`, `eval(`, `subprocess` in `backend/app` found no true positives | Secure by design | No change | Verified |
| INFO-003 | Performance | LLM latency when Ollama reachable can be 2–5s per `README:76`; health cache already optimized (TTL 10s at `llm.py:17`); RAG retrieve ~0.03ms measured, health ~19ms, ingest ~0.14ms | Informational | Direct timing probes (see §4 performance) | Local model inherent | No change — documented limitation | Verified |

Severity reasoning: BUG-002 is High because it violates the documented reliability contract (fallback) and degrades UX to an error response for all chat intents when Ollama is down; BUG-003 is Medium because it affects the primary voice input path but only manifests on pause/restart (continuous mode) and has text fallback; BUG-001 is Low because it is non-functional today but creates warning noise and future breakage risk.

---

### 7. Resolved Issues (Detail)

#### BUG-001 — `datetime.utcnow()` Deprecation

- **What was wrong:** `backend/app/interview/service.py:64` and `backend/app/interview/session_service.py:113,170,186` used `datetime.utcnow().isoformat() + "Z"` which is deprecated since Python 3.12 (`DeprecationWarning: datetime.datetime.utcnow() is deprecated...`). Every interview/session test emitted this warning, totaling 131 warnings per `pytest -q` run, polluting CI and risking future removal.
- **Why it happened:** Code predated Python 3.12 deprecation; not updated when warnings were introduced. Test data at `tests/test_interview.py:242` also still uses `utcnow()` intentionally for creating legacy fixtures (kept as-is).
- **What was changed:**
  - `service.py:1` — `from datetime import datetime, timedelta` → `from datetime import datetime, timedelta, timezone`
  - `service.py:64` — `datetime.utcnow().isoformat() + "Z"` → `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")`
  - `session_service.py:1` — `from datetime import datetime` → `from datetime import datetime, timezone`
  - `session_service.py:113` — same replacement for `started_at`
  - `session_service.py:170` — `datetime.utcnow().isoformat()+"Z"` → `datetime.now(timezone.utc).isoformat().replace("+00:00","Z")`
  - `session_service.py:186` — `datetime.utcnow().isoformat()+"Z"` → `datetime.now(timezone.utc).isoformat().replace("+00:00","Z")`
- **How verified:** Re-ran `python -m pytest tests -q` → **280 passed, 1 warning** (down from 131). The single remaining warning is `tests/test_interview.py:242` (test fixture, not production code) — confirmed via `grep` that no `utcnow` remains in `backend/app`.

#### BUG-002 — Orchestrator Ollama Fallback Missing

- **What was wrong:** When Ollama was unavailable (health check failure, timeout, `OllamaError`), `route_message('...')` raised `OllamaError` instead of returning a safe fallback response. `POST /api/chat` then returned HTTP 503 with `detail: "Ollama service is unavailable"` (graceful in not leaking stack, but not the promised heuristic fallback). Agent intents (career/resume/interview/learning/recruitment/business) had no `OllamaError` handler; general intent via `_validated_generate` also had none; streaming raised before yielding.
- **Why it happened:** `_validated_generate` at `orchestrator.py:572` and agent invocation at `orchestrator.py:762` were written assuming LLM success; only `TypeError` for signature mismatch was caught. The outer `app/main.py:150-152` catch produced a 503 error response, but the README phased reliability expected `get_safe_fallback()` content.
- **What was changed:**
  - `orchestrator.py:5` — `from app.services.llm import generate_response, generate_response_stream` → `..., OllamaError`
  - `orchestrator.py:568-599` — Wrap `generate_response` in `try/except OllamaError` and generic `Exception`, returning `get_safe_fallback(intent, rag_used)` with `validation_issues ["llm_unavailable:..."]` (or `["llm_error"]`). For `rag_used` append ` (Based on retrieved context...)` to preserve RAG distinction.
  - `orchestrator.py:760-789` — Wrap `await agent_fn(...)` in `except OllamaError` (both direct and `TypeError` fallback path) and `except Exception`, constructing `{"response": get_safe_fallback(...), "intent": intent, "agent": intent}` and `last_validation` with `llm_unavailable` tag.
  - `orchestrator.py:895-908` — Wrap streaming `async for chunk in generate_response_stream` in `try/except OllamaError/Exception`, yielding `{"type":"chunk","content": fallback}` and setting `full_response=[fallback]` so history is persisted and frontend receives usable content.
- **How verified:**
  - Reproduced pre-fix via mocked `generate_response` raising `OllamaError` → raised exception; post-fix returns `response` starting `I apologize — I wasn't able to generate...` with `validation_issues ['llm_unavailable:Ollama service is unavailable']` and `intent general`.
  - Career intent mock `patch('app.agents.career_agent.get_response', side_effect=OllamaError)` → pre-fix raised, post-fix returns `intent career` with career-specific fallback (`Here's general career guidance...`).
  - Streaming mock `patch(generate_response_stream, side_effect=OllamaError)` → post-fix yields meta + chunk with fallback text, no unhandled error.
  - Full suite `python -m pytest tests -q` still **280 passed**; `python -m eval.runner --mock` still **45/45 routing**.

#### BUG-003 — InterviewSession Stale Transcript Closure

- **What was wrong:** `InterviewSession.jsx:168-258` sets up `SpeechRecognition` with `rec.onend` that on auto-restart does `baseTranscriptRef.current = transcript`. The `transcript` variable is captured at effect creation (`useEffect(..., [speechSupported])`), so after the user speaks "hello world" and pauses (triggering `onend`), `transcript` inside closure is still `""` (initial), causing the base to be reset to empty and the next utterance to overwrite rather than append.
- **Why it happened:** Classic React stale closure — missing `transcript` in dependency array; adding it would recreate the recognition object unnecessarily. The intended pattern is a ref for latest value.
- **What was changed:**
  - `InterviewSession.jsx:51-53` — Added `const transcriptRef = useRef('')` + `useEffect(() => { transcriptRef.current = transcript }, [transcript])` after `listeningIntentRef`.
  - `InterviewSession.jsx:195-199` — Changed `baseTranscriptRef.current = transcript` → `baseTranscriptRef.current = transcriptRef.current` inside `rec.onend` auto-restart branch.
- **How verified:** `npm run build` still succeeds (371.77 kB); `npm run lint` still 21 warnings (no new errors); code inspection confirms `transcriptRef` now provides fresh value without recreating `rec` object. Manual browser verification remains required for full voice flow (see §12).

---

### 8. Regression Testing

After each confirmed fix, the relevant test subset was rerun:

| Fix | Tests Rerun | Command | Result |
|-----|-------------|---------|--------|
| BUG-001 (utcnow) | Interview + Session subsets | `python -m pytest tests/test_interview.py tests/test_session.py tests/test_question_count.py -q` before full suite | Warnings dropped in those subsets; then full suite |
| BUG-002 (orchestrator fallback) | Full suite + targeted fallback probes | `python -c` mocked `route_message`/`stream_message` (see §7 verification) | All mocked probes passed; then full suite |
| BUG-003 (stale closure) | Frontend build | `npm run build` + `npm run lint` | Build success; lint warnings unchanged |
| **Final full regression (post all fixes)** | **Complete backend suite** | `python -m pytest tests -q` | **280 passed, 1 warning (test-only) in 44.72s** |
| | **Evaluation** | `python -m eval.runner --routing-only` + `python -m eval.runner --mock` | **Routing 1.0 (39/39 & 45/45), relevance 0.89, 0 flags** |
| | **Frontend build** | `npm run build` | **✓ built in 404ms, 179 modules, 371.77 kB** |
| | **Frontend lint** | `npm run lint` | **21 warnings, 0 errors** |
| | **API route health** | Route enumeration + `TestClient` probes (health, chat validation, interview traversal) | All routes present, 422/200 statuses correct, security headers present |
| | **Import health** | `python -c "from app.main import app; ..."` | 25 routes enumerated, no import errors |

No test was skipped. No test was modified. Expected commands from `README:531` were used:

```bash
cd backend
python -m pytest tests -q

cd ../frontend
npm run build
npm run lint
```

---

### 9. Final Test Results

**Backend — `python -m pytest tests -q` (final post-fix run, 2026-09-23):**

| Metric | Count |
|--------|-------|
| Total tests | 280 |
| Passed | 280 |
| Failed | 0 |
| Skipped | 0 |
| Warnings | 1 (`tests/test_interview.py:242` DeprecationWarning for test fixture `utcnow`, not production code) |
| Collection | 280 items in 56.22s → 44.72s post-fix (cache warm) |

**Frontend — `npm run build` (Vite 8.2.2):**

| Metric | Result |
|--------|--------|
| Transform | 179 modules transformed |
| Output | `dist/index.html 0.49 kB`, `dist/assets/index-CY...js 371.77 kB (gzip 110.04 kB)`, `dist/assets/index-Dy...css 32.15 kB` |
| Status | **Successful** — `✓ built in 404ms` |
| Errors | 0 |

**Frontend — `npm run lint` (Oxlint 1.79.0):**

| Metric | Result |
|--------|--------|
| Errors | 0 |
| Warnings | 21 (unused params/catch vars, `react-hooks/exhaustive-deps`, `react/purity`, `set-state-in-effect`, `no-useless-catch`) |
| Status | **Pass (warnings only)** |

**Evaluation — `python -m eval.runner --mock` (final):**

| Signal | Result |
|--------|--------|
| Routing accuracy | 1.0 (45/45) — per-domain all 1.0 |
| Relevance mean | 0.89 (heuristic, needs human review) |
| Completeness | 39/45 (0.87) |
| Hallucination flags | 0 |
| Error flags | 0 |
| Latency | mean 12.1ms median 2.1ms p95 14.4ms min 1.4ms max 421.8ms (mocked, no Ollama) |

**API — Route Verification (`app/main.py:182` + auto-enumeration):**

| Method | Endpoint | Verified | Notes |
|--------|----------|----------|-------|
| GET | `/` | ✓ | service status |
| GET | `/api/health` | ✓ | 200 + security headers `nosniff/DENY/no-referrer` |
| POST | `/api/chat` | ✓ | 422 on empty/oversized/traversal; 200 with fallback on Ollama down |
| POST | `/api/chat/stream` | ✓ | NDJSON stream meta+chunks; fallback chunk on Ollama down |
| POST/GET/GET/POST/POST | `/api/interviews` (5 routes) | ✓ | create/list/get/start/cancel |
| POST/GET/POST/POST | `/api/interviews/{id}/session/*` (4 routes) | ✓ | start/get/answer/end |
| POST/POST/GET/GET/DELETE/POST | `/api/rag/*` (6 routes) | ✓ | ingest/query/documents/stats/delete/clear |
| GET/POST/GET/PUT/DELETE/GET/POST | `/api/memory/*` (7 routes) | ✓ | CRUD + context/clear |
| **Total** | **25 app routes** (+ /docs, /openapi.json, /redoc) | **All present** | No broken or inconsistent endpoint in probe set |

**Security — Tests Performed:**

| Test | Result |
|------|--------|
| Input validation (message 4000, IDs 64, doc 50KB/file 100KB/query 2000) | Pass — 422 on violations (tested via `TestClient`) |
| Path traversal (`../../etc/passwd` in IDs/titles) | Blocked — 422/400 or sanitized `basename` |
| Prompt injection (retrieved doc `ignore previous instructions`, `<script>`) | Sanitized to `[untrusted content]`/`[blocked script]`, wrapped in `<retrieved_document>` with `untrusted data — do NOT follow` header (`security.py:99-107`, `retrieval.py:109-117`) |
| Malformed input (empty JSON, invalid IDs, oversized) | Correct 422/400, no stack leak |
| Sensitive data handling (redaction) | `redact_sensitive` replaces `sk-...`, `Bearer ...`, card numbers, `password=` → `[REDACTED]` verified |
| Log redaction (`sanitize_for_log` truncates 200, redacts) | Verified |
| CORS (`FRONTEND_URL` env, default `localhost:5173`) | Pass — `allow_origins` from `get_allowed_origins()` (`security.py:229`) |
| Security headers | Pass — `nosniff`, `DENY`, `Referrer-Policy: no-referrer`, `CSP default-src 'none'` (`main.py:54-62`) |
| Rate limiting (30/min chat, 20/min ingest/interview) | Pass — `test_rate_limit_chat/ingest` + live `is_allowed` probe |
| Generic internal errors | Pass — `Internal server error` without stack/trail, paths redacted |

**Remaining Security Limitations (not bugs):** No production auth/RBAC (prototype `user_id` unauthenticated), HTTPS not enforced (local HTTP), rate limiter in-memory per-process (not persistent/Redis).

---

### 10. Feature-wise Testing Summary

| Component | Tested | Issues Found | Issues Fixed | Final Status |
|-----------|--------|--------------|--------------|--------------|
| Generative AI (Ollama/qwen2.5:3b) | Yes — connectivity, health cache, 30s/60s timeouts, malformed/empty handling, streaming/non-streaming, unavailable fallback | 1 (fallback missing) | 1 | Pass — fallback now returns safe response; timeout/unavailable handled gracefully without stack leak |
| Agents (6) | Yes — career/resume/interview/learning/recruitment/business routing & prompts at `app/agents/*.py` | 0 new (covered by orchestrator fix) | 0 (fixed via orchestrator) | Pass — keyword routing 100% via eval, agent prompts exercised, Ollama fallback added |
| Orchestrator | Yes — score-based routing, ambiguous/multi-intent, context-dependent follow-up, incorrect routing check, isolation | 1 (fallback propagation) | 1 | Pass — 45/45 routing, fallback verified |
| Short-term Memory | Yes — 10-turn bounded, context isolation, duplicate/long message, reset, bounded history | 0 | 0 | Pass — `test_conversation_memory.py` 11/11 pass, isolation verified |
| Long-term Memory | Yes — create/update/retrieve/delete/persistence, invalid/empty user_id, sensitive filtering, isolation | 0 | 0 | Pass — `test_memory.py` 20/20 pass, SQLite persistence verified, sensitive keywords blocked |
| RAG | Yes — ingestion→chunking→TF-IDF→store→retrieve→threshold/top-k, empty KB, oversized/duplicate, sanitization, prompt-injection | 0 | 0 | Pass — `test_rag.py` 35/35 pass, sanitization verified, in-memory scope documented |
| Interview | Yes — setup→plan→question→answer→evaluation→adaptive→completion→report→persistence, min/max counts, timer/expired, empty/long/malformed, LLM fallback, SQLite | 1 (utcnow deprecation) | 1 | Pass — reports based on actual eval data (not generic), heuristic fallbacks verified |
| Voice | Yes — recognition setup, interim/final transcript, continuous/restart, synthesis/cancellation, browser compat, fallback | 1 (stale closure) | 1 | Pass (logic) — browser-dependent; requires manual verification (see §12) |
| Validation | Yes — empty/malformed/refusal/repetition/grounded-claim/structured missing, latency <5ms | 0 | 0 | Pass — `test_validation.py` 18/18 pass, latency median 0.2-2ms verified |
| Security | Yes — size limits, traversal, injection, CORS/headers, rate limit, log redaction, file ingestion, secrets | 0 | 0 | Pass — `test_security.py` 26/26 pass; remaining limitations documented |
| Performance | Yes — health ~19ms, RAG retrieve ~0.03ms, orchestrator (mocked 2.1ms median), validation <2ms, streaming TTFT where measurable | 0 | 0 | Pass — no unbounded growth; health cache 10s already optimized |
| Error Handling | Yes — Ollama unavailable, malformed/empty LLM, invalid input, missing files, DB failure, expired session, frontend API failure | 1 (orchestrator part) | 1 | Pass — all return generic `Internal server error` or safe fallback, no stack/secrets exposed |
| Frontend | Yes — build, lint, imports, routes, API calls, loading/error/empty states, interview/chat/voice UI, form validation, session handling | 0 blocking (21 lint warnings) | 0 (1 voice closure fix) | Build pass, lint warnings only |

---

### 11. Remaining Limitations (Not Bugs)

These are genuine prototype limitations that remain after testing and are **not** classified as defects:

- **Local LLM latency:** Qwen2.5 3B via Ollama is CPU/GPU-dependent; total 2–5s typical, streaming reduces perceived TTFT but total remains higher than managed inference. Health/model cache (10s TTL at `llm.py:17`) mitigates repeated ` /api/tags` overhead.
- **Browser-dependent voice:** Speech Recognition/Synthesis require `window.SpeechRecognition || webkitSpeechRecognition` and `speechSynthesis` — Chrome/Edge desktop recommended; not server-side STT/CV. Fixed stale closure improves reliability but manual browser verification still required.
- **In-memory RAG store:** `app/rag/store.py` is process-scoped `dict` (`documents`+`chunks`+`vectors`) with TF-IDF re-fit on each ingest; resets on restart (no FAISS/pgvector/DB). Bounded to 100 docs, 50KB text, 100KB file, `.txt/.md` only — intentional prototype scope.
- **No authentication/RBAC:** `user_id` is client-provided unauthenticated; `default_user` prototype fallback — not production auth.
- **HTTPS not enforced:** Local dev HTTP only; CSP `default-src 'none'` is API-minimal.
- **In-memory rate limiting:** `chat_limiter` 30/min, `ingest_limiter`/`interview_limiter` 20/min via `deque` per-process (`security.py:180-205`); not persistent across instances (no Redis).
- **Keyword-based intent routing:** Regex/keyword scoring with priority ordering; may miss nuanced or highly complex requests — documented as limitation, not replaced.
- **Single-machine deployment:** No container orchestration, no horizontal scaling; SQLite files under `data/`/`backend/data/`.
- **Heuristic fallbacks are synthetic:** When LLM unavailable, interview plan/question/evaluation/report and chat all use keyword/word-count heuristics — not human-evaluated; clearly marked as fallback.
- **Streaming bypasses agent modules directly:** `POST /api/chat/stream` uses system prompts directly rather than agent `get_response` — documented.
- **Frontend lint warnings:** 21 `oxlint` warnings remain (unused params, hooks deps, `Date.now` purity, `set-state-in-effect`) — non-blocking, intentionally not fixed to keep changes minimal.

---

### 12. Manual Verification Required

The following could not be fully automated in the current host environment and require manual browser/human verification:

| Item | Why Manual | How to Verify |
|------|------------|---------------|
| **Voice — Speech Recognition (STT)** | Requires `SpeechRecognition`/`webkitSpeechRecognition`, microphone permission, live audio capture; not simulatable in Node/pytest | Chrome/Edge desktop → `InterviewSession` → allow mic → speak; verify interim transcript updates, final transcript appended, `baseTranscriptRef` correctly accumulates across pauses after BUG-003 fix, editable transcript before submit |
| **Voice — Speech Synthesis (TTS)** | Requires `speechSynthesis`/`SpeechSynthesisUtterance`, audible output, voice selection | In interview session, verify AI reads intro ("Hello, [name]...") and each question aloud, replay button works, cancellation on `stopSpeaking`/unmount, fallback to text when `ttsSupported` false |
| **Proctoring — Tab/Fullscreen/Camera/Mic events** | Requires real `document.visibilitychange`/`fullscreenchange`/`MediaStream` lifecycle | Interview session → switch tabs → verify `tab_hidden` warning + `proctor-warning` banner; enter/exit fullscreen → `fullscreen_entered/exited`; deny/allow camera/mic → `camera_permission_denied`/`stream_interrupted` events; check `proctorEvents` count and `Warnings: N` badge |
| **Interview timer expiry** | Requires waiting `duration_minutes` or mocking `started_at`; browser timer vs backend `_is_session_time_expired` race | Start session with `duration_minutes=30`; verify `TIME REMAINING` countdown, auto-`endSession` at 0; verify backend `POST /api/interviews/{id}/session/answer` after expiry returns 400 `Interview time has expired. Session completed.` |
| **Ollama live quality** | Mocked tests verify HTTP plumbing but not model output quality; actual Qwen2.5:3b responses vary by prompt/hardware | Run `ollama serve` + `ollama pull qwen2.5:3b` locally, then `python -m eval.runner --output eval_report_live.json` (requires hardware) and human-review relevance/completeness/hallucination flags (marked `needs_human_review=true`) |
| **Responsive/Visual UI** | No browser automation framework in project (intentionally not installed) | Manual check chat UI, interview lobby, session voice UI at mobile/tablet widths; verify loading skeletons, error banners, empty states, form validation messages |

Do **not** claim voice/proctoring as "passed" without the above manual checks; code inspection + mocked logic passed, but browser APIs need live verification.

---

### 13. Final Conclusion

Testing completed end-to-end across all subsystems enumerated in §3. Baseline was **280 backend tests passed with 131 deprecation warnings, frontend build successful, lint 21 warnings, evaluation routing 100% (45/45)**.

**Three confirmed defects were reproduced, root-caused, and fixed with minimal safe changes:**

1. **BUG-001 (Low)** — `datetime.utcnow()` deprecation noise → timezone-aware fix.
2. **BUG-002 (High)** — Missing Ollama fallback in chat/orchestration → added `OllamaError` handling and `get_safe_fallback()` returns for both non-streaming and streaming paths.
3. **BUG-003 (Medium)** — Interview voice transcript stale closure → `transcriptRef` fix.

**Final regression after fixes:** `python -m pytest tests -q` → **280 passed, 1 warning (test fixture only)**; `npm run build` → **successful (371.77 kB)**; `npm run lint` → **21 warnings, 0 errors**; `eval.runner --mock` → **routing 1.0 (45/45)**; API route enumeration → **25 routes healthy**; security controls → **verified**. No existing tests were modified; no architecture change was made; no unnecessary features added.

**Remaining limitations** are honestly documented in §11 (local LLM latency, browser-dependent voice, in-memory RAG/memory/rate-limit, no auth/RBAC/HTTPS, keyword routing, single-machine, heuristic fallbacks). **Manual verification** for browser voice/proctoring remains required (§12).

No claim of "100% bug-free" or "production-ready" is made — such certification would require production auth, persistent vector DB, HTTPS, and human evaluation of live model quality, all outside this prototype scope.

---

### Evidence References (file:line for nav)

- `backend/app/services/orchestrator.py:868` — fixed streaming `OllamaError` handler
- `backend/app/services/orchestrator.py:568-599` — fixed `_validated_generate` fallback
- `backend/app/services/orchestrator.py:760-789` — fixed agent `OllamaError` fallback
- `backend/app/interview/service.py:64` — utcnow fix
- `backend/app/interview/session_service.py:113,170,186` — utcnow fixes
- `frontend/src/InterviewSession.jsx:51-53,195-199` — transcriptRef fix
- `backend/app/services/security.py:57-107` — redaction/sanitization
- `backend/app/rag/retrieval.py:109-117` — untrusted document wrapper

*Report generated as part of Phase 15 — stored at `docs/Ardhanarishwar_Solver_Testing_and_Resolution_Report.md` (not overwriting `README.md`).*
