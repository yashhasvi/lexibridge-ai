# Folder: pipelines

## Overview

This folder contains the following files and their summaries.

## Files

### __init__.py

# File: __init__.py

## Purpose
Initialize and expose data module pipelines to the outside world.

## Key Components
* Import various pipeline components from submodules, including:
	+ Orchestrator and PipelineConfig
	+ Ingest-related classes (load_source, get_source, IngestValidator)
	+ Transformation classes (Normalizer, SemanticDeduplicator, Enricher)
	+ Chunking and embedding classes (Chunker, Strategy, BatchEmbedder)
* Expose all imported components to the module's namespace using __all__

## Important Logic
None. This is a simple import and re-export module.

## Dependencies
- .orchestrator: Orchestrator and PipelineConfig
- .ingest: load_source, get_source, IngestValidator
- .transform: Normalizer, SemanticDeduplicator, Enricher
- .chunk: Chunker, Strategy
- .embed: BatchEmbedder
- .graph: TripleExtractor, GraphBuilder

## Notes
This module serves as an entry point for the data module's pipelines.

---

### orchestrator.py

# File: orchestrator.py

## Purpose
The `orchestrator` is a pipeline that runs the full ETL (Extract, Transform, Load) process for a given source. It includes stages such as ingest, validation, normalization, enrichment, and storage.

## Key Components
- **PipelineConfig**: A class that loads and parses configuration settings from a dictionary.
- **Orchestrator**: The main pipeline orchestrator class, responsible for running the ETL process.
- **IngestValidator**, **Normalizer**, **Enricher**, **Chunker**, **BatchEmbedder**, and **GraphBuilder** are various stage-specific classes used in the pipeline.

## Important Logic
- The `Orchestrator` class runs the following stages:
  - Ingest: Loads data from a source.
  - Validate + Dedup: Validates and removes duplicates using content hashes.
  - Normalize: Strips HTML, cleans text.
  - Enrich (NER): Performs named entity recognition.
  - Store Canonical Parquet: Stores canonical records in Parquet format.
  - Chunk → Embed → Store: Chunks data, embeds with a specified model, and stores in Parquet + LanceDB.
  - Graph: Builds the graph using Triples and stores in GraphStore.

## Dependencies
- `pipeline_cfg`: A dictionary containing configuration settings for the pipeline.
- `raw_dir`: The directory path where raw source files are stored.
- `parquet_store`, `lance_store`, and `graph_store`: Storage objects used to store data in Parquet, LanceDB, and GraphStore formats, respectively.

## Notes
- The orchestrator supports various sources, including Wikidata, which has a special pipeline path for graph-first data.

---

