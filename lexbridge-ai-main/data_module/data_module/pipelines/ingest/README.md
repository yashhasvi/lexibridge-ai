# Folder: ingest

## Overview

This folder contains the following files and their summaries.

## Files

### validator.py

# File: validator.py
## Purpose
Validate CanonicalQA records and deduplicate by content_hash using a two-level deduplication approach.

## Key Components
- `IngestValidator` class: responsible for validating and deduplicating records
- SQLite database: stores seen content hashes across runs
- Pydantic validation: validates record fields on construction

## Important Logic
- Two-level deduplication:
  - Exact deduplication: checks if content_hash is already in the database
  - Optional semantic deduplication: uses cosine similarity above a threshold
- Validation and processing of records: checks for valid fields, text length, and duplicates

## Dependencies
- `pydantic`: for Pydantic validation
- `sqlite3`: for SQLite database operations
- `pathlib`: for file path manipulation
- `logging`: for logging statistics

## Notes
- This class is designed to be used as a context manager (`with` statement) to ensure proper cleanup of the database connection.

---

### __init__.py

# File: __init__.py

## Purpose
This file serves as the entry point for the ingest pipeline in the data module. It exposes functions and classes necessary for ingesting data.

## Key Components
- `load_source` function to load a source
- `get_source` function to retrieve a source
- `IngestValidator` class to validate ingested data

## Important Logic
None, this file primarily acts as an entry point and imports necessary components from other modules.

## Dependencies
- `.loader` module for loading sources
- `.validator` module for validating ingested data

## Notes
This file is part of the `data_module.pipelines.ingest` package and exports functions and classes to be used in the ingest pipeline.

---

### loader.py

# File: loader.py

## Purpose
Load data from a specified source and feed it downstream.

## Key Components
- `get_source`: Instantiate a source connector by name.
- `load_source`: Download and parse a source, yielding CanonicalQA records.

## Important Logic
The code uses the `SOURCE_REGISTRY` to get an instance of a source connector. It then yields CanonicalQA records from the source's iterator.

## Dependencies
- `pathlib`
- `logging`
- `typing`

## Notes
This file is responsible for loading data from various sources, including those registered in the `SOURCE_REGISTRY`.

---

