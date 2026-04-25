# Folder: embed

## Overview

This folder contains the following files and their summaries.

## Files

### batch.py

# File: batch.py

## Purpose
Batch embedder that processes ChunkRecords in batches and adds embeddings.

## Key Components
- `BatchEmbedder` class that handles embedding of ChunkRecords in batches.
- Uses `get_embedder` function to get an embedder instance for the specified model.
- Embeds text using the embedder and updates ChunkRecord metadata with embedding model and dimension.

## Important Logic
- Embedding is done in batches with a specified batch size (256 by default).
- Retries are handled with exponential backoff for transient failures (network/GPU OOM).
- If all retries fail, chunks are returned without embeddings.

## Dependencies
- `chunk` module for ChunkRecord schema.
- `.embedder` module for get_embedder function.

## Notes
- The embedder instance is cached to avoid repeated initialization.
- Logging is used to track embedding progress and errors.

---

### __init__.py

# File: __init__.py

## Purpose
This file is the entry point for the `data_module.pipelines.embed` module, allowing users to import and utilize its components.

## Key Components
* `get_embedder`: a function that returns an embedder instance based on user configuration.
* `SentenceTransformersEmbedder`, `OpenAIEmbedder`, `BatchEmbedder`: classes implementing different types of embedders.

## Important Logic
None, as this file primarily serves as a module registry and does not contain any complex logic.

## Dependencies
* `.embedder` submodule, which contains the `get_embedder` function and embedder classes.
* `.batch` submodule, which provides the `BatchEmbedder` class.

## Notes
This file is likely used in conjunction with other modules to provide a unified interface for working with various types of embeddings.

---

### embedder.py

# File: embedder.py

## Purpose
Generates dense vector embeddings for ChunkRecords using sentence-transformers and OpenAI text-embedding APIs.

## Key Components
* `SentenceTransformersEmbedder`: uses the sentence-transformers library to generate embeddings.
* `OpenAIEmbedder`: uses the OpenAI API to generate embeddings (requires OPENAI_API_KEY env var).
* `get_embedder` function: factory that returns the correct embedder based on model name prefix.

## Important Logic
* The embedding model name and dimension are stored in ChunkRecord.metadata for safe rebuilding of the index.
* Embedders use a lazy loading mechanism to load models only when needed.

## Dependencies
* sentence-transformers library
* OpenAI API (requires OPENAI_API_KEY env var)
* numpy

## Notes
* Supports both local (sentence-transformers) and remote (OpenAI) embedding APIs.

---

