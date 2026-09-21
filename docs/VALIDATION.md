# Validation — Phase 7 Lightweight AI Response Validation

No large model, no expensive pipeline, latency <5 ms for checks, at most one retry.

## Goal
Reduce poor, malformed, or unsupported AI responses before they reach user, while preserving good responses and keeping chat/interview architecture, Qwen/Ollama, and frontend unchanged.

## What is checked (backend/app/services/validation.py)

1. **Empty** — `not text.strip()` → `empty_response`. Too-short greetings allowed (preserves "hi", "hello").
2. **Malformed** — prompt leakage (`assistant: assistant:` , `<|im_start|>`), unclosed ``` , raw JSON (`{"topics":` ) in chat, `<script` injection. Intent-aware (allows JSON for interview).
3. **Refusal / error artifacts** — regex for `as an ai language model`, `i cannot fulfill`, `i am unable`, plus `ollama.*unavailable`, `failed to connect`, `empty response from model`, `500.*error`, `timeout`. Catches LLM or infra artifacts without flagging normal advice ("I can provide general guidance").
4. **Excessive repetition** — char 8× `(.)\1{7,}`, word 5× `\b(\w+)(?:\s+\1){4,}`, 4/5-gram repeated ≥4, sentence duplicate ≥2 (long) or ≥3. Skips len<40 except char/word repeat to avoid short greeting false positives.
5. **Invalid structured output** — where JSON expected (interview plan/question/report/evaluation), type checks.
6. **Missing required fields** — plan: `topics` list 5-10 and each `name`; question: `question` ≥10 chars, `topic`; report: 8 required keys with score 0-10 and list checks; evaluation: 5 scores 0-10.
7. **Unsupported grounded claims (RAG)** — `according to company policy`, `based on retrieved documents`, `samplecorp.*policy`, numeric `\d+ days.*leave` **with `rag_used=False`** → `unsupported_grounded_claim`. When `rag_used=True`, claim allowed (citation check is advisory, not failing).

For RAG: `format_context` already distinguishes retrieved vs generated; validation ensures we don't present numeric policy as fact without retrieval and fallback says "No approved documents were found...".

## How it is used

- **Orchestrator** (`app/services/orchestrator.py:40`): `validate_chat_response(text, intent, rag_used, rag_results, message)` after `generate_response` or `agent_fn`. Returns `is_valid, issues, should_retry, latency_ms`.
  - `should_retry` only for `empty`/ `malformed:prompt_leakage` (transient). Retry once with appended `[Validation note: previous response was malformed/empty, please provide concise well-formed answer…]`, bounded, no infinite loop.
  - Otherwise fallback via `get_safe_fallback(intent, rag_used)` — intent-specific 1-2 sentence general guidance, no hallucination. For RAG, adds "(Based on retrieved context where available…)".
  - Result includes `validation_issues`, `validation_passed`, `validation_latency_ms`; history stores sanitized fallback if invalid.
  - Streaming: validates final assembled text before writing to history (already streamed chunks not retried to keep latency bounded).
- **Interview** (`app/interview/engine.py:12`, `evaluator.py:1`): `validate_plan/question/final_report/evaluation` after `normalize_*`. On failure, log and use heuristic fallback (`_heuristic_plan`, `_fallback_question`, `_heuristic_report`, `_heuristic_eval`).

## Fallback examples

- `intent=career`: "I apologize — I wasn't able to generate a complete response at the moment. Here's general career guidance: consider clarifying your current skills, target role, and timeline, and I can provide a phased plan…"
- `intent=general` + `rag_used=False`: "…Please try rephrasing your question, and I'll provide general best-practice guidance (without claiming live browsing…)"
- `rag_used=True` failure: adds "(Based on retrieved context where available; general guidance otherwise.)"

## Latency

- Validation itself: regex only, `0.2–2 ms` per call, avg <2 ms for 120 samples (test `test_latency_bounded` asserts `avg <5 ms` and `single <5 ms`).
- Retry: at most one extra LLM call (30 s timeout, same as original), rarely triggered (only empty/malformed). No retry for repetition/grounded/refusal → fallback.
- Evaluation (`python -m eval.runner --mock`): median 2.8 ms, p95 11.1 ms, mean 13.2 ms (vs pre-validation median 1.0 ms) — no material degradation; routing still 1.0 (45/45), no hallucination/error flags.

## Tests

`backend/tests/test_validation.py` (18 tests):
- `test_empty_responses`, `test_successful_response_preserved` (preserves greetings, markdown)
- `test_malformed_prompt_leakage`, `test_refusal_error_artifacts`, `test_excessive_repetition` (char, word, sentence, n-gram)
- `test_unsupported_grounded_claims` (without/with RAG, numeric policy)
- `test_invalid_structured_output_plan`, `test_missing_fields_question/final_report/evaluation`
- `test_safe_fallback`
- Integration: `test_validation_integration_orchestrator_empty_retry_and_fallback`, `test_validation_retry_success` (empty→good via retry), `test_validation_fallback_for_unsupported_claim`, `test_validation_preserves_good_response`
- `test_latency_bounded` (120 calls avg <5 ms)
- `test_interview_validation_fallback`, `test_malformed_detection_preserves_valid`

All 254 tests pass (including prior phases).

## What is NOT done

- No second LLM as judge
- No frontend redesign (only added validation metadata to response dict for observability)
- No Qwen/Ollama replacement
- No infinite retry (max 1)
- No heavy preprocessing

## Running

```bash
cd backend
python -m pytest tests/test_validation.py -v
python -m pytest tests/ -q
python -m eval.runner --mock
python -m eval.runner --mock --output eval_report_validation.json
```
