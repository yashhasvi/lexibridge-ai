# File: fetcher_registry.py

## Purpose
Fetcher registry that manages references to all available retrieval backends.

## Key Components
- `LightRAGFetcher`: A wrapper around the LightRAGClient HTTP API, exposing an interface compatible with the AbstractFetcher classes.
- `FetcherRegistry`: Holds active fetchers keyed by FetcherName constants.

## Important Logic
- The registry populates at startup from existing data_module fetchers using the `register` method.
- The `LightRAGFetcher` class uses asyncio to make HTTP requests and returns dicts compatible with the internal RetrievedChunk format.

## Dependencies
- `asyncio`
- `logging`
- `typing`

## Notes
- The registry is populated at startup, but new fetchers can be registered dynamically using the `register` method.