# Folder: schema

## Overview

This folder contains the following files and their summaries.

## Files

### graph.py

# File: graph.py

## Purpose
Construction of a knowledge graph using triples, entities, and relations.

## Key Components
- **Entity**: A node in the knowledge graph with attributes like entity ID, type, label, description, and properties.
- **Triple**: A directed edge in the graph representing relationships between entities, e.g., subject --[predicate]--> object.
- **SubGraph**: A retrieved subgraph containing a seed entity/question and its neighborhood.

## Important Logic
- Triple derivation from CanonicalQA records using the graph extractor pipeline stage.
- Entity linking to the Wikidata backbone through `wikidata_id`.

## Dependencies
- `pydantic` for data modeling.
- `provenance` module for predicate types and source names.

## Notes
- The knowledge graph serves as the foundation for Graph RAG and entity linking.
- Classes have been designed with flexibility in mind, accommodating various entity types and triple properties.

---

### __init__.py

# File: __init__.py

## Purpose
 Defines and exports Pydantic models for various data records in a structured manner.

## Key Components
- Importing Pydantic models from related modules.
- Exporting a list of models through the `__all__` variable.

## Important Logic
None; This is an initializer file, setting up imports and exports rather than containing core logic.

## Dependencies
- Various Pydantic model classes (e.g., `CanonicalAnswer`, `ChunkMetadata`) from related modules within the same package.

## Notes
This module acts as a central location for importing and exporting data models used across different components or features of the application. It's designed to provide easy access to these models, likely for serialization, deserialization, or other data management purposes.

---

### chunk.py

# File: chunk.py

## Purpose
Define the schema for ChunkRecords, which are retrieval units stored in the vector index.

## Key Components
- `ChunkRecord` class represents a single retrieval chunk.
- `ChunkMetadata` class stores denormalized metadata alongside every chunk.
- The file utilizes Pydantic's `BaseModel` and various Field parameters.

## Important Logic
The `to_lance_row` method is used to flatten the `ChunkRecord` into a dictionary suitable for LanceDB insertion.

## Dependencies
- `pydantic`
- `.provenance` module (for `ChunkType`, `License`, and `SourceName`)

## Notes
This file is part of a larger codebase that appears to be implementing a Retrieval Augmented Generation (RAG) model. The ChunkRecord schema is designed for efficient storage in a vector database (LanceDB).

---

### canonical.py

# File: canonical.py

## Purpose
Normalizes QA records from various data sources into a standardized format, providing a source-of-truth model for downstream processing.

## Key Components
- `CanonicalQA`: Normalized QA record with attributes such as id, title, body, answers, and provenance information.
- `EntityMention`: Represents named entities found in question or answer bodies, including surface form, entity type, start and end character indices, and wikidata ID (if available).
- `CanonicalAnswer`: Represents a single answer to a question with attributes such as answer id, body, score, is_accepted, author id, created at time, and entity mentions.

## Important Logic
- The `compute_hash` method calculates the content hash of the QA record based on title, body, and best answer body.
- The `sorted_answers` property sorts answers by accepted status first, then by score descending.
- The `attribution_str` method generates a short attribution string for CC BY-SA compliance.

## Dependencies
- `pydantic` library for model definition and validation.
- `hashlib` library for computing SHA256 hashes.

## Notes
- The code uses UUIDs as canonical IDs to resolve source IDs to canonical IDs.
- Provenance information, such as license and source URL, is stored in the `CanonicalQA` model.

---

### provenance.py

# File: provenance.py

## Purpose
Defines enums for provenance and license information used across schema models.

## Key Components
- `License` enum with common licenses (CC BY-SA, CC0, Apache 2.0, etc.)
- `SourceName` enum with various data sources (StackExchange, Wikipedia, Wikidata, etc.)
- `ChunkType` enum for chunk derivation methods (Canonical QA, Question Only, Answer Only, etc.)
- `PredicateType` enum for knowledge graph edge labels (Answers, Accepted For, Tags With, etc.)

## Important Logic
None

## Dependencies
- `enum` module from Python's standard library

## Notes
Enums are defined as subclasses of `str` to enable use with string values.

---

