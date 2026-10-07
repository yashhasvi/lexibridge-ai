# File: schema.py

## Purpose
Define the typed schema for multi-source answers, including BrainResponse and SourceCard dataclasses.

## Key Components
* `BrainResponse`: Complete multi-source answer produced by the brain pipeline.
* `SourceCard`: One retrieved passage contributing to the final answer.
* `AnswerType` and `RetrievalMethod` enums: Define types of answers and retrieval methods.
* `RetrievalTrace`: Per-fetcher latency and result count telemetry.

## Important Logic
The schema is used as a canonical output format for every component in the pipeline. The `ResponseFormatter` handles JSON serialization.

## Dependencies
* `dataclasses`
* `enum`
* `typing`

## Notes
* This file defines the typed schema for multi-source answers, which are used throughout the pipeline.
* The schema includes dataclasses for BrainResponse and SourceCard, as well as enums for AnswerType and RetrievalMethod.