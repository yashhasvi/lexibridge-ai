# File: __init__.py

## Purpose
Orchestrates data deduplication, grouping, and ranking for the CrossEncoderReranker.

## Key Components
- `MultiSourceAggregator` class responsible for data processing pipeline.
- Exact deduplication, optional semantic deduplication, re-grouping by fetcher, RRF fusion, and trimming to top-N.

## Important Logic
- Data processing pipeline consists of 5 steps:
    1. Exact deduplication using `exact_dedup` function.
    2. Optional semantic deduplication using `semantic_dedup` function if threshold is set.
    3. Re-grouping by fetcher registration name for RRF fusion using `group_by_source` function.
    4. RRF fusion using `rrf_merge` function with fetched weights.
    5. Trimming to top-N chunks.

## Dependencies
- `deduplicator`: exact dedup and semantic dedup functions.
- `rrf_merger`: RRF fusion function.
- `source_grouper`: re-grouping by fetcher registration name function.
- Logging module for debugging purposes.

## Notes
- Requires sentence-transformers library for semantic deduplication.
- Adds latency of approximately 100ms if semantic dedup is enabled.