# Folder: config

## Overview

This folder contains the following files and their summaries.

## Files

### pipeline.yaml

# File: pipeline.yaml

## Purpose
Define the configuration for a natural language processing (NLP) pipeline.

## Key Components
- **Chunking**: Strategy to split text into smaller chunks.
- **Embedding**: Use sentence transformers to embed text data.
- **NER/Enrichment**: Apply named entity recognition and enrichment using spaCy models.
- **Text Cleaning**: Clean and preprocess text data by removing HTML tags, normalizing whitespace, and filtering out short texts.
- **Deduplication**: Remove duplicate records based on exact hash or semantic similarity.
- **Parallelism**: Utilize multiple workers to process batches of data in parallel.

## Important Logic
The pipeline uses a combination of pre-processing techniques (chunking, embedding, text cleaning) and post-processing techniques (deduplication). It utilizes spaCy for NER/enrichment tasks and sentence transformers for embedding. The pipeline also enables parallelization with multiple workers and configurable batch sizes.

## Dependencies
- **sentence-transformers/all-MiniLM-L6-v2**: Sentence transformer model for embedding.
- **en_core_web_sm**: SpaCy model for NER/enrichment.
- **spacy_n_process**: Number of CPU cores to use for spaCy processing.
- **OPENAI_API_KEY** (optional): Required for using text-embedding-3-small.

## Notes
- The pipeline can be customized by modifying the settings in this configuration file.
- Different models and techniques can be tried out based on specific needs and requirements.

---

### storage.yaml

# File: storage.yaml

## Purpose
Configure data storage settings for various services.

## Key Components
- **Data Root**: Root directory for all stored data (`./data`).
- Storage configurations for:
  - Parquet archive with partitioning and compression.
  - DuckDB database for analytics over Parquet.
  - LanceDB hot vector index.
  - SQLite pipeline state and ID mappings.
  - Graph storage using either NetworkX or Neo4j.

## Important Logic
The file uses environment variables (e.g., `${data_root}`, `${NEO4J_PASSWORD}`) to parameterize configuration settings. 

## Dependencies
- Requires the `NEO4J_PASSWORD` environment variable for Neo4j authentication.
- Possibly depends on other services like Parquet, DuckDB, and LanceDB.

## Notes
The file also includes a commented-out section describing an alternative approach using SQLite adjacency tables for graph storage.

---

