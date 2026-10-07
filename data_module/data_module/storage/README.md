# Folder: storage

## Overview

This folder contains the following files and their summaries.

## Files

### __init__.py

# File: `__init__.py`

## Purpose
This file serves as the entry point for data module, providing a registry and factory for various storage backends.

## Key Components
* The `build_stores` function constructs all storage backends from a configuration dictionary.
* The `ParquetStore`, `DuckDBStore`, `LanceStore`, and `SQLiteStore` classes represent different storage backends.
* The `get_graph_store` function returns a graph store instance based on the provided configuration.

## Important Logic
The `build_stores` function resolves paths using the `resolve` helper function, which replaces placeholders with the actual data root path. It also unwraps the top-level 'storage' key from the configuration dictionary if present.

## Dependencies
* `pathlib`: for working with file paths
* `.base`: for the `AbstractStore` class
* `.parquet_store`, `.duckdb_store`, `.lance_store`, and `.sqlite_store`: for specific storage backend implementations

## Notes
The `build_stores` function returns a dictionary mapping storage backends to their instances. The `get_graph_store` function is likely a factory method that creates graph stores based on the provided configuration.

---

### sqlite_store.py

# File: sqlite_store.py

## Purpose
Lightweight state management for the pipeline using SQLite. Tracks pipeline run history, source ID mapping, download status, and checkpoints.

## Key Components
- `SQLiteStore` class, an implementation of `AbstractStore`
- Database schema with tables for:
  - Pipeline runs
  - Source ID mapping
  - Download status
  - Checkpoints (incremental ingestion watermarks)
- Methods for interacting with the database, including CRUD operations and checkpoint management

## Important Logic
- The database is created on demand when an instance of `SQLiteStore` is initialized.
- The `_DDL` string contains SQL queries to create tables if they do not exist.
- The `write_checkpoint` method uses JSON to store arbitrary metadata for each source.

## Dependencies
- `sqlite3`
- `logging`

## Notes
- This implementation assumes a SQLite database file will be created at the specified path.
- The checkpoint data is stored in plain text as JSON, which may not be suitable for large-scale production use.

---

### parquet_store.py

# File: parquet_store.py

## Purpose
Parquet store implementation for CanonicalQA and ChunkRecord data. Provides methods to write and read partitioned Parquet files.

## Key Components
- `ParquetStore` class, extending `AbstractStore`
- `_CANONICAL_SCHEMA` and `_CHUNK_SCHEMA` arrow schemas
- Methods:
  - `write_canonical`: writes CanonicalQA records to Parquet
  - `write_chunks`: writes ChunkRecord data to Parquet
  - `read_canonical` and `read_chunks`: read partitioned Parquet files

## Important Logic
- Uses PyArrow for schema-enforced writes and predicate pushdown reads
- Partitions data by source and year for efficient filtered reads
- Writes data in batch sizes (default: 10,000) to optimize performance

## Dependencies
- `pyarrow` library for Parquet operations
- `pyarrow.parquet` module for reading/writing Parquet files
- `pathlib` for file path management
- Logging module for error reporting and info messages

## Notes
- Data is stored in the following directory layout:
  ```
  canonical/source=stackexchange/year=2024/part-0001.parquet
  chunks/source=stackexchange/year=2024/part-0001.parquet
  ```

---

### lance_store.py

# File: lance_store.py

## Purpose
The `lance_store` module is a data store that integrates with LanceDB to provide fast semantic RAG retrieval capabilities. It supports storing ChunkRecords with dense embeddings in a LanceDB table and enables ANN search, scalar metadata filtering, and hybrid BM25+dense search.

## Key Components
- **LanceStore class**: Wraps a LanceDB table for vector + metadata storage and retrieval.
- **upsert_chunks method**: Inserts or overwrites chunks in the LanceDB table.
- **search method**: Performs ANN vector search with optional filters.
- **create_index method**: Creates an ANN index for fast retrieval after bulk load.

## Important Logic
The `LanceStore` class lazily creates a LanceDB table on first write, inferring its schema from the first batch of ChunkRecords. It provides methods for upserting chunks, searching with optional filters, and creating an ANN index for efficient retrieval. The `_infer_schema` function generates a PyArrow schema from a sample LanceDB row dictionary.

## Dependencies
- **LanceDB**: A library providing fast vector search capabilities.
- **PyArrow**: A Python library for working with Apache Arrow data formats.
- **logging**: A module for logging messages during execution.

## Notes
This module is designed to be used in conjunction with the `lancedb` and `pyarrow` libraries, providing a convenient interface for integrating with LanceDB. The `create_index` method supports creation of both IVF-PQ and HNSW-SQ indices based on user preferences.

---

### graph_store.py

# File: graph_store.py

## Purpose
The `graph_store` module provides a dual-backend adapter for storing and querying graphs, supporting both NetworkX (in-process) and Neo4j (production) backends.

## Key Components

*   Two main classes:
    *   `NetworkXGraphStore`: A lightweight in-process graph store backed by NetworkX.
    *   `Neo4jGraphStore`: A production-grade graph store backed by Neo4j, supporting Cypher queries and complex traversals.
*   Methods for storing entities and triples, retrieving subgraphs, and querying neighbors.

## Important Logic

*   Both `NetworkXGraphStore` and `Neo4jGraphStore` implement the `AbstractStore` interface.
*   The `upsert_entities` method creates or updates entity nodes in the graph store.
*   The `upsert_triples` method adds relationships between entities in the graph store.
*   The `get_subgraph` method returns a subgraph centered around a given entity, with optional depth parameter.

## Dependencies

*   `networkx`
*   `neo4j` (for Neo4jGraphStore)
*   `pandas` (not explicitly listed as dependency, but used in the code)

## Notes

*   The module uses logging to provide informative output for debugging and monitoring.
*   Pickle is used to serialize NetworkX graphs for storage.

---

### base.py

# File: base.py

## Purpose
Provides the abstract interface for all storage backends.

## Key Components
- `AbstractStore` class: defines the basic methods for storage backends.
- `close`: method to close the store, marked as abstract due to being specific to each backend.
- Context manager support through `__enter__` and `__exit__`.

## Important Logic
The class uses the ABC (Abstract Base Class) module to define an interface that must be implemented by any concrete storage backend.

## Dependencies
- `abc`: Abstract Base Classes
- `typing`: for type hints

## Notes
This file defines the foundation for all storage backends, requiring them to implement specific methods for handling data storage and retrieval.

---

### duckdb_store.py

# File: duckdb_store.py

## Purpose
Store and analyze Parquet files using DuckDB, a fast SQL database.

## Key Components
* `DuckDBStore` class: Wraps a DuckDB connection to store and query data.
* Methods:
	+ `_register_views`: Registers Parquet datasets as views in the DuckDB database.
	+ `query`: Executes SQL queries on the stored data.
	+ Convenience analytics queries:
		- `source_summary`
		- `top_tags`
		- `score_distribution`

## Important Logic
* The store connects to a DuckDB database using `duckdb.connect`.
* Data is registered as views in the database using `CREATE OR REPLACE VIEW` statements.
* SQL queries are executed on the stored data using `self._conn.execute`.

## Dependencies
* `duckdb`: Fast SQL database library.
* `logging`: Library for logging messages.

## Notes
* This code uses DuckDB's ability to register Parquet files as views, allowing for fast and efficient querying of the data.
* The convenience analytics queries provide pre-defined SQL queries for common analysis tasks.

---

