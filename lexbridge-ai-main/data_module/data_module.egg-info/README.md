# Folder: data_module.egg-info

## Overview

This folder contains the following files and their summaries.

## Files

### PKG-INFO

# File: PKG-INFO

## Purpose
The `data_module` is a modular QA data ingestion, storage, and retrieval pipeline for RAG and knowledge graphs.

## Key Components
- Modular design with per-source downloaders, parsers, mappers, and ETL stages
- Supports various storage backends (Parquet, DuckDB, LanceDB, SQLite, Graph)
- Fast vector index using LanceDB for semantic RAG
- Knowledge graph storage using NetworkX/Neo4j

## Important Logic
- Pipeline architecture handles raw data → canonical QA format
- Attribution requirements for CC BY-SA sources
- Quickstart scripts for downloading and running the pipeline

## Dependencies
Requires Python 3.10+, along with various dependencies:
- `pydantic>=2.0`
- `python-dotenv>=1.0`
- `pyyaml>=6.0`
- `rich>=13.0`
- `typer>=0.12`
- `tqdm>=4.66`
- `pyarrow>=15.0`
- `pandas>=2.0`
- `duckdb>=0.10`
- `lancedb>=0.6`
- `beautifulsoup4>=4.12`
- `html2text>=2024.2`
- `spacy>=3.7`
- `langdetect>=1.0`
- `sentence-transformers>=3.0`
- `numpy>=1.26`
- `networkx>=3.2`
- `datasets>=2.18`
- `huggingface-hub>=0.22`
- `httpx>=0.27`
- `aiofiles>=23.2`
- `py7zr>=0.21`
- `rank-bm25>=0.2`

## Notes
- The project structure includes scripts, config files, and storage backends.
- Attribution requirements for CC BY-SA sources must be followed to ensure compliance with licensing terms.

---

### SOURCES.txt

# File: SOURCES.txt

## Purpose
The file contains a list of sources, likely related to data or dependencies, used in the project.

## Key Components
- The file is part of an egg-info package.
- It lists various files and directories within the `data_module` structure.
- Some entries suggest involvement with specific datasets (e.g., HotpotQA, Squad) or formats (e.g., SQLite store).

## Important Logic
None explicitly mentioned; likely used for packaging purposes.

## Dependencies
None specified in this file. Dependencies are listed elsewhere in the project's configuration files (e.g., `pyproject.toml`, `requirements.txt`).

## Notes
This file seems to be automatically generated as part of the project's build process, listing all included sources in a structured format for packaging and distribution purposes.

---

### entry_points.txt

# File: entry_points.txt

## Purpose
Define console scripts for the application.

## Key Components
- List of console scripts with their corresponding entry points.

## Important Logic
None, as this is a configuration file defining entry points for the console.

## Dependencies
- `data_module` package, which contains the script modules for each console script.

## Notes
This file defines three console scripts: `data-download`, `data-index`, and `data-pipeline`. Each script corresponds to an entry point in the `data_module.scripts` module.

---

### requires.txt

# File: requires.txt

## Purpose
This file specifies the required dependencies for a project.

## Key Components
* The file is formatted as a `requirements.txt` file, which lists dependencies in the format `package_name>=version`.
* There are three sections:
	+ `[dev]`: dependencies required for development and testing.
	+ `[neo4j]`: dependency required for Neo4j interactions.
	+ `[openai]`: dependency required for OpenAI interactions.

## Important Logic
None, this file simply lists dependencies with their versions.

## Dependencies
* Development dependencies: `pytest`, `pytest-asyncio`, `black`, `ruff`, and `mypy`.
* Production dependencies: various packages including data science and machine learning libraries.
* Additional dependencies: `neo4j` and `openai`.

## Notes
This file is likely used by a package manager like pip to install the required dependencies for the project.

---

### top_level.txt

# File: top_level.txt

## Purpose
Unknown. The file only contains a single word, "data_module", without any further explanation.

## Key Components
None specified

## Important Logic
No logic is present in the file

## Dependencies
Unknown

## Notes
The file appears to be incomplete or lacking essential information

---

