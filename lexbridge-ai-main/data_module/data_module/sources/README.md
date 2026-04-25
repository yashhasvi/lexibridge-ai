# Folder: sources

## Overview

This folder contains the following files and their summaries.

## Files

### hf_base.py

# File: hf_base.py

## Purpose
Download and cache Hugging Face datasets locally.

## Key Components
- `HFDownloader`: Downloads a Hugging Face dataset to local cache.
  - Supports streaming downloads for large datasets.
  - Caches entire dataset locally then truncates/skips rows if needed.
- `HFParser`: Reads cached Parquet files and yields rows as dictionaries.

## Important Logic
- The downloader uses the `datasets` library to download and cache the dataset.
- The parser reads the cached Parquet files using pandas.

## Dependencies
- `datasets`
- `pandas`

## Notes
- This code is used by various Hugging Face datasets, including SQuAD, NQ, MS MARCO, HotpotQA, TriviaQA, and OASST2.

---

### __init__.py

# File: __init__.py

## Purpose
Registry module for data source connectors.

## Key Components
* `SOURCE_REGISTRY`: a dictionary mapping connector names to their respective classes.
* Various data source classes (e.g. StackExchangeSource, WikipediaSource) inherited from `AbstractDataSource`.

## Important Logic
The module initializes the `SOURCE_REGISTRY` dictionary with entries for each supported data source connector.

## Dependencies
None explicitly listed, but inherits from `.base` module.

## Notes
This module serves as a centralized registry for data source connectors.

---

### base.py

# File: base.py

## Purpose
Abstract base classes for source connectors to implement the data pipeline.

## Key Components
* `AbstractDownloader`: downloads raw source files to a local directory.
* `AbstractParser`: reads raw files and yields dicts (source-specific structure).
* `AbstractMapper`: maps source-specific raw dicts to CanonicalQA records.
* `AbstractDataSource`: orchestrates downloader, parser, and mapper for a single source.

## Important Logic
The pipeline's loader calls `iter_canonical()` which chains all three components: download, parse, and map. The pipeline can be separated into three concerns:
1. Download once and cache raw files.
2. Re-parse without re-downloading.
3. Re-map (e.g. after schema changes) without re-parsing.

## Dependencies
* `canonical`: for the `CanonicalQA` class.
* `pathlib`: for file system operations.
* `logging`: for logging purposes.
* `typing`: for type hints.

## Notes
The code uses abstract classes and methods to provide a framework for implementing specific source connectors. Each connector must implement the three components (downloader, parser, mapper) and inherit from the base classes. The `iter_canonical()` method orchestrates the entire pipeline.

---

