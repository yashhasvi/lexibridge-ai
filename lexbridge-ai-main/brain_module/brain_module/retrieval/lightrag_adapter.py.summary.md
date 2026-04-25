# File: lightrag_adapter.py
## Purpose
LightRAG client and adapter for ingesting CanonicalQA records into LightRAG server.

## Key Components
- `LightRAGClient`: Thin async HTTP client wrapping the LightRAG server REST API.
  Provides methods for checking health, inserting documents, querying, and closing the connection.
- `LightRAGIngestionAdapter`: Adapter that streams CanonicalQA records into LightRAG.

## Important Logic
- `canonical_qa_to_lightrag_doc(qa: Any) -> dict[str, Any]`: Converts a CanonicalQA dataclass/Pydantic model to the LightRAG insert payload.
- `LightRAGIngestionAdapter.ingest_batch(qa_records: list[Any], batch_size: int = 20, concurrency: int = 4) -> list[dict[str, Any]]`: Ingests records in batches with progress logging.

## Dependencies
- `httpx` for making HTTP requests.
- `logging` for logging important events.
- `dataclasses` and `typing` for working with data structures.

## Notes
The code uses asynchronous programming to interact with the LightRAG server efficiently. The adapter provides a convenient way to ingest large amounts of CanonicalQA records into LightRAG in batches, which can be controlled by parameters like batch size and concurrency.