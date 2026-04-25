# File: main.py

## Purpose
FastAPI application for Brain Module with various endpoints and features.

## Key Components

*   Multiple fetchers (e.g., FastRAGFetcher, HybridFetcher, GraphRAGFetcher) that handle data retrieval from different sources.
*   LightRAGClient and LighTRAGIngestionAdapter for interacting with LightRAG server.
*   SynthesisEngine and ResponseFormatter for generating responses to user queries.
*   CrossEncoderReranker and RagasEvaluator for evaluating response quality.

## Important Logic

*   `_register_data_module_fetchers` function initializes fetchers from `.env` file and registers them in the `FetcherRegistry`.
*   Application uses environment variables (e.g., LLM_BACKEND, LIGHTRAG_URL, REDIS_URL) to configure its behavior.
*   Guardrail-related environment variables (e.g., MIN_RERANK_SCORE, MAX_SAME_SOURCE) are used to enable or disable certain features.

## Dependencies

*   `fastapi` for building the application
*   `uvicorn` for running the application
*   `pydantic` for data validation and serialization
*   `python-dotenv` for loading environment variables from `.env` file
*   Various third-party libraries (e.g., `sentence-transformers`, `neo4j`, `langdetect`) used by different components

## Notes

*   Application uses asynchronous programming with `asyncio` to handle concurrent requests.
*   It employs caching mechanisms (e.g., `EmbeddingCache`, `QueryCache`) to improve performance.
*   Response formatting and synthesis are handled by separate components (`ResponseFormatter`, `SynthesisEngine`).