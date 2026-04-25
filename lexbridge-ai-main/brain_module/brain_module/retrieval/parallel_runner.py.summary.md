# File: parallel_runner.py

## Purpose
This module implements a `ParallelFetcher` class that runs multiple fetchers concurrently using asyncio.gather. It supports both synchronous and asynchronous fetchers.

## Key Components
- `_run_fetcher`: an async function that runs a single fetcher and returns its results.
- `ParallelFetcher`: a class that aggregates the results of multiple fetchers.

## Important Logic
The `ParallelFetcher` class uses the `asyncio.gather` function to run multiple fetchers concurrently. It normalizes the results from each fetcher using the `_normalise_chunk` function, which ensures that all expected keys exist in the chunk dicts.

## Dependencies
- `asyncio`: for concurrent execution of fetchers.
- `logging`: for logging errors and debug messages.
- `FetcherRegistry`: a registry of registered fetchers.
- `RetrievalTrace`: a dataclass representing per-fetcher latency telemetry.

## Notes
The module uses environment variables to configure the fetcher timeout. It also provides a way to run multiple fetchers concurrently, making it efficient for large-scale queries.