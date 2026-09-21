# Evaluation Framework — Ardhanarishwar Solver Phase 1

Lightweight, maintainable evaluation for the existing AI system. No dashboard, no external APIs, no architecture change.

## What is measured

| Signal | How | Ground truth? |
|---|---|---|
| **Intent routing** | `orchestrator.detect_intent` / `_detect_with_context` vs `expected` in dataset | Yes — routing is deterministic code, automated accuracy is reliable |
| **Response relevance** | Keyword recall: fraction of `expected_keywords` found in response | No — heuristic. Human review required. Keywords are loose proxies. |
| **Response completeness** | Word count ≥20, sentence count, bullet/list detection | No — structural proxy only. Human review required for actual completeness. |
| **Context awareness** | For `CONTEXT_CASES`, does second-turn response contain `context_check` keyword from first turn | No — cheap substring check. Human review required for real context understanding. |
| **Hallucination / error** | Substring scan for forbidden claims (`live job listings`, `browsed internet`, `ATS score is 87`, etc.) + `OllamaError` / empty / too_short flags | Partially — catches obvious verbatim claims; will miss paraphrased hallucinations. Human review required. |
| **Latency** | `time.perf_counter()` around `route_message` | Yes — wall-clock measurement, accurate to ms. |

> **Important:** Automated relevance/completeness/hallucination scores are NOT ground truth. The report explicitly marks `needs_human_review=true` for every case and prints `Note: Automated heuristics are NOT ground truth.`

## Dataset

- `eval/dataset.py:DATASET` — 35 single-turn cases, 5 per domain (career, resume, interview, learning, recruitment, business, general)
- `eval/dataset.py:EDGE_CASES` — 5 edge/hallucination probes (live listings, browsing, ATS score, ambiguous, empty)
- `eval/dataset.py:CONTEXT_CASES` — 3 multi-turn sequences testing follow-up routing + memory (`career→learning`, `recruitment→recruitment`, `interview→interview`)

Total evaluated in full run: 35 + 4 (non-skipped edges) + 6 context turns = **45 cases**.

## How to run

```bash
cd backend

# Fastest — routing only, no LLM, <1s
python -m eval.runner --routing-only
python -m eval.runner --routing-only --output eval_report_routing.json

# Mocked full evaluation — offline, no Ollama needed, deterministic
python -m eval.runner --mock
python -m eval.runner --mock --output eval_report_mock.json

# Live — hits Ollama via orchestrator (requires `ollama serve` + `qwen2.5:3b`)
python -m eval.runner
python -m eval.runner --output eval_report_live.json

# Also via pytest (unit tests for the framework itself)
python -m pytest tests/test_eval.py -v
```

## Output

- Console: `=== Ardhanarishwar Solver Evaluation Summary ===` with per-domain routing accuracy, latency (mean/median/p95/min/max), relevance mean, completeness pass rate, hallucination/error counts, and top routing failures.
- JSON (if `--output`): `{ summary: {...}, results: [SingleResult], context_details: [...] }` with full response capture per case.

## Maintenance

- Add cases by appending to `DATASET` / `EDGE_CASES` / `CONTEXT_CASES` in `eval/dataset.py` — no code change needed.
- Adjust thresholds in `eval/runner.py:score_completeness` (`min_words`) or `DEFAULT_FORBIDDEN_PHRASES` as needed.
- Do NOT modify orchestrator to make evaluation pass — the dataset is fixed and evaluation is read-only.

## Non-goals

- No frontend changes
- No new dependencies beyond standard library + existing `app.*`
- No vector DB / RAG / external LLM APIs
- No persistent evaluation DB — JSON files are sufficient for Phase 1
