# File: retrieval_filter.py

## Purpose
Filter reranked chunks before LLM synthesis to prevent low relevance, score gaps, and source dominance.

## Key Components
- `filter_low_relevance`: Drops chunks below an absolute score threshold.
- `filter_score_gap`: Drops chunks far below the top-scored chunk (relative).
- `cap_source_diversity`: Prevents one source from dominating synthesis slots.

## Important Logic
Each filter function:
  - Processes input list of chunks (dicts with "score" and optionally "source").
  - Keeps or drops chunks based on its respective logic.
  - Logs informative messages for debugging purposes.

## Dependencies
- `logging` module: For logging informative messages.
- `collections.Counter`: To count source occurrences in `cap_source_diversity`.

## Notes
- The filters work independently, but can be chained to create more complex filtering logic.
- The functions assume input chunks have "score" and optionally "source" keys.