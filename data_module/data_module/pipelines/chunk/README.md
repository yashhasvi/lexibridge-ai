# Folder: chunk

## Overview

This folder contains the following files and their summaries.

## Files

### strategies.py

# File: strategies.py
## Purpose
The `strategies` module provides a set of chunking algorithms for splitting CanonicalQA records into smaller chunks suitable for embedding and vector index storage.

## Key Components
*   The `Strategy` enum defines five different chunking strategies:
    *   `CANONICAL_QA`: One chunk per record, including question title, body, and best answer.
    *   `PER_ANSWER`: One chunk per answer, with the question context included.
    *   `MULTI_HOP`: Separate chunks for question and each supporting passage (for HotpotQA-style records).
    *   `QUESTION_ONLY`: Only the question text is used for query-side indexing.
    *   `HIERARCHICAL`: A parent question chunk with child answer chunks linked via `parent_chunk_id`.
*   The `STRATEGY_MAP` dictionary maps `Strategy` enums to their corresponding implementation functions.

## Important Logic
Each strategy function takes a CanonicalQA record and optional parameters as input. They return a list of ChunkRecord objects, which contain the processed text, metadata, and other relevant information.

Some key logic includes:
*   Text truncation: Records are truncated to fit within a specified maximum token count (512 by default).
*   Chunk ID generation: Unique IDs are generated for each chunk using UUIDs.
*   Metadata creation: ChunkMetadata objects are created based on the input record's metadata and additional information.

## Dependencies
The module relies on several dependencies:
*   `__future__.annotations`: Enables type hinting for Python 3.x.
*   `enum`: Provides support for enumerations.
*   `typing`: Used for type hinting.
*   `uuid`: For generating unique IDs.

## Notes
The code appears well-structured, with clear and concise implementation functions. The use of enums and dictionaries makes the code more maintainable and easier to extend. However, some minor improvements could be made:
*   Consider adding docstrings or comments to explain the purpose of each strategy function.
*   Ensure consistent naming conventions throughout the module (e.g., using snake_case for variable names).

---

### chunker.py

# File: chunker.py

## Purpose
Applies a chunking strategy to a stream of CanonicalQA records and yields ChunkRecord objects ready for embedding.

## Key Components
- `Chunker` class with methods:
  - `__init__`: initializes the chunker with a strategy and optional max tokens.
  - `chunk`: chunks a single record into multiple ChunkRecords.
  - `chunk_stream`: chunks a stream of records into multiple ChunkRecords.
- `STRATEGY_MAP` dictionary maps strategy names to functions.

## Important Logic
The `Chunker` class uses the provided strategy function from `STRATEGY_MAP` to chunk each record, and stores the used strategy in the metadata of each resulting ChunkRecord. The `chunk_stream` method iterates over a stream of records, chunks each one, and yields the resulting ChunkRecords.

## Dependencies
- `logging`: for logging information about chunking.
- `typing`: for type hints.
- `schema.canonical`: for CanonicalQA record schema.
- `schema.chunk`: for ChunkRecord schema.
- `.strategies`: for strategy functions.

## Notes
This code uses a Strategy design pattern to allow different chunking strategies to be used. The current implementation includes a default "CANONICAL_QA" strategy, but other strategies can be added by registering them in the `STRATEGY_MAP`.

---

### __init__.py

# File: __init__.py

## Purpose
Initialization file for the data module's pipelines chunk functionality.

## Key Components
- `strategies`: Module containing strategy definitions and mappings.
- `chunker`: Chunking logic for data processing.

## Important Logic
None specific, serves as an import initializer.

## Dependencies
- `.strategies` (module)
- `.chunker` (module)

## Notes
Exports key components for use in the data module.

---

