# File: rrf_merger.py

## Purpose
Fuses multiple ranked lists using Reciprocal Rank Fusion (RRF) to produce a single ranked list.

## Key Components
- `rrf_merge` function merges ranked lists using RRF.
- `_fallback_id` function generates a stable id from text when `chunk_id` is absent.
- Constants: `RRF_K = 60` (smoothing constant).

## Important Logic
- RRF formula: `score(d) = Σ_r  1 / (k + rank_r(d))`.
- Fuses score replaces individual fetcher scores for downstream re-ranking.

## Dependencies
- `typing` module.
- `hashlib` module.

## Notes
- Returns a single flat list of chunk dicts, sorted by descending RRF score.