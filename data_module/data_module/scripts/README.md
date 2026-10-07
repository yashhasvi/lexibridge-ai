# Folder: scripts

## Overview

This folder contains the following files and their summaries.

## Files

### build_index.py

# File: build_index.py

## Purpose
Builds and manages vector and graph indexes for a data repository.

## Key Components
- `build` command to create or rebuild vector indexes in LanceDB.
- `rebuild-graph` command to rebuild the graph index from Parquet files.
- `stats` command to display index and store statistics.

## Important Logic
- Index creation involves reading data from storage stores (LanceDB, Parquet).
- Graph rebuilding uses a `GraphBuilder` object to process CanonicalQA records.
- Statistics display includes chunk counts in LanceDB and source summaries.

## Dependencies
- Required libraries: typer, yaml, json, logging, data_module.storage, data_module.pipelines.graph.builder

## Notes
- The script assumes the existence of storage.yaml and data directories.
- Index creation may fail if dependencies are not properly set up.

---

### download_sources.py

# File: download_sources.py

## Purpose
This script is a CLI tool for downloading raw source data files using various sources (e.g. Stack Exchange, Squad).

## Key Components
- The script uses the `typer` library to create a command-line interface.
- It loads configuration files from YAML files in the `config/sources` directory.
- It utilizes a registry of available sources (`SOURCE_REGISTRY`) to determine which sources to download.

## Important Logic
The main logic is contained within the `main` function, which iterates over the specified sources and attempts to download data for each one. If a source's configuration file does not exist or if the data has already been downloaded (and skipping exists), it skips that source.

## Dependencies
- `typer`
- `logging`
- `yaml`

## Notes
This script uses a registry of available sources (`SOURCE_REGISTRY`) which is imported from another module. The actual logic for downloading data is contained within this other module, and is not shown here.

---

### __init__.py

# File: __init__.py

## Purpose
Initializes a data module with scripts.

## Key Components
- A single comment indicating the contents of the file ("data_module.scripts").

## Important Logic
None, as this is an empty file containing only a comment.

## Dependencies
Unknown, as there are no import statements or references to external dependencies.

## Notes
This file appears to be a placeholder for future implementation.

---

### run_pipeline.py

# File: run_pipeline.py

## Purpose
Run the full ETL pipeline for one or more sources using the `data-pipeline` CLI tool.

## Key Components
*   `app`: The main application instance of the `typer` library, which defines the command-line interface (CLI).
*   `_load_yaml`: A function that loads YAML configuration files from disk.
*   `Orchestrator`: An object responsible for orchestrating the ETL pipeline stages.

## Important Logic
The script uses the `typer` library to define a CLI tool with three commands:
*   `run`: Runs the full ETL pipeline for one or more sources. It loads YAML configuration files, builds storage stores, and executes the pipeline.
*   `status`: Displays ingestion checkpoints and pipeline run history.
*   `backfill-checkpoints`: Backfills source_checkpoints from already-ingested canonical Parquet data.

## Dependencies
The script depends on several external libraries:
*   `typer`: A library for building command-line interfaces (CLI).
*   `yaml`: A library for parsing YAML configuration files.
*   `pathlib`: A library for working with file paths and directories.
*   `logging`: A library for logging messages.

## Notes
The script assumes the presence of specific directory structures and configuration files. It also uses a checkpoint system to keep track of ingestion progress.

---

