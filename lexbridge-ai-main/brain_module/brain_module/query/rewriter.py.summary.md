# File: rewriter.py

## Purpose
Query rewriting module that expands ambiguous or short queries into multiple retrieval variants.

## Key Components
- `QueryRewriter` class with methods for rewriting queries using LLM (Large Language Model) and heuristic fallback.
- Environment variables for enabling/disabling query rewriting and setting max variants.

## Important Logic
- The original query is always included as variant #1 to ensure retrieval quality never degrades.
- Two strategies: LLM-based and heuristic fallback, with the latter used when LLM is unavailable or disabled.
- `rewrite` method takes a query string and returns a list of query variants (original first).

## Dependencies
- `logging`
- `re`
- `typing`
- Environment variables (`QUERY_REWRITE_ENABLED`, `QUERY_REWRITE_MAX_VARIANTS`)

## Notes
- Supports asynchronous operations with `async/await` syntax.
- LLM-based rewriting uses a fast LLM call to generate 2-3 query variants.