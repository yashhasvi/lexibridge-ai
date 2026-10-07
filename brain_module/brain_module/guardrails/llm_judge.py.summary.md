# File: llm_judge.py

## Purpose
Optional LLM-as-judge implementation for second-pass validation using a lightweight LLM call.

## Key Components
- Gated behind `ENABLE_LLM_JUDGE=true` to avoid extra latency and cost.
- Uses an LLM (or cheaper model) to ask yes/no questions about answer quality.
- Returns verdict with boolean outcome and reason.

## Important Logic
- `judge_response` function asks the LLM for evaluation and returns a `JudgeVerdict`.
- `LLMClient` is used to complete LLM calls, with fail-open handling on errors.

## Dependencies
- `logging`: for logging warning messages.
- `dataclasses`: for defining `JudgeVerdict` class.
- `typing`: for type hints (e.g. `LLMClient`, `str`, `bool`).

## Notes
- This implementation is optional and can be disabled by setting `ENABLE_LLM_JUDGE=false`.
- The LLM is used as a strict quality-assurance reviewer to evaluate answer quality.