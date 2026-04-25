# File: complexity_scorer.py

## Purpose
Determine which fetchers to activate for a query based on its complexity and intent.

## Key Components
- `FetcherPlan` dataclass: represents the plan for which fetchers to run and their weights.
- `ComplexityScorer` class: decides which fetchers to activate based on query intent and complexity.
- Heuristic helpers (e.g. `_compute_complexity`, `_count_tokens`, etc.) that provide signals for scoring.

## Important Logic
The `ComplexityScorer` uses a routing table to determine the plan based on query intent and complexity. The plan includes which fetchers to run, their weights, and a reasoning string.

## Dependencies
- `IntentClassifier`: used to classify the query's intent.
- `FetcherName` constants: represent the names of different fetcher strategies.

## Notes
The code uses a combination of heuristics (e.g. token count, named entity recognition) to score complexity, as well as IntentClassification to determine intent. The routing table is based on the interaction between these two signals.