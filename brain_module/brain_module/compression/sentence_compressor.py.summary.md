# File: sentence_compressor.py

## Purpose
Extractive sentence-level context compression for retrieval chunks.

## Key Components
- Sentence splitting using regex heuristics.
- Cosine similarity computation between sentences and query.
- Sentence ranking and keeping top-N per chunk.
- Chunk reassembly with compressed text.

## Important Logic
- `_split_sentences` function splits text into sentences using regex patterns.
- `compress` method compresses chunks by filtering out irrelevant sentences.
- `_get_embedder` method initializes the sentence embedder model.

## Dependencies
- `sentence-transformers` library for sentence embeddings.
- `numpy` library for numerical computations.

## Notes
- Environment variables can be used to configure compression settings.
- Compression is purely extractive, no LLM call required.