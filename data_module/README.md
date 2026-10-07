# Folder: data_module

## Overview

This folder contains the following files and their summaries.

## Files

### pyproject.toml

# File: pyproject.toml

## Purpose
Configures the project's build system, dependencies, and metadata.

## Key Components

* **Build System**: The `build-system` section specifies the requirements for building the project using `setuptools` as the backend.
* **Project Metadata**: The `[project]` section contains metadata about the project, including its name, version, description, license, and dependencies.
* **Dependencies**: The project depends on various packages, categorized into core, data processing, text processing, embeddings, graph, Hugging Face, HTTP/downloads, and BM25/hybrid search libraries.
* **Optional Dependencies**: Some dependencies are marked as optional, including `neo4j`, `openai`, and `dev` tools for testing and formatting.

## Important Logic

* The project requires Python 3.10 or higher to run.
* The project uses `setuptools` as the build backend with version 68 or higher.
* The project has several scripts defined in the `[project.scripts]` section, including `data-download`, `data-pipeline`, and `data-index`.

## Dependencies

### Core Libraries

* `pydantic`
* `python-dotenv`
* `pyyaml`
* `rich`
* `typer`
* `tqdm`

### Data Processing

* `pyarrow`
* `pandas`
* `duckdb`
* `lancedb`

### Text Processing

* `beautifulsoup4`
* `html2text`
* `spacy`
* `langdetect`

### Embeddings

* `sentence-transformers`
* `numpy`

### Graph

* `networkx`

### Hugging Face

* `datasets`
* `huggingface-hub`

### HTTP / Downloads

* `httpx`
* `aiofiles`
* `py7zr`

### BM25 / Hybrid Search

* `rank-bm25`

## Notes

* The project uses the `CC-BY-SA-4.0` license.
* The project has a README file named `README.md`.
* The project uses various tools for testing and formatting, including `pytest`, `black`, and `ruff`.

---

