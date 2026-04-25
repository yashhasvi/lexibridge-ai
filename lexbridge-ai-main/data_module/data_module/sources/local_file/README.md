# Folder: local_file

## Overview

This folder contains the following files and their summaries.

## Files

### __init__.py

# File: __init__.py

## Purpose
Local file ingest module that reads CSV and JSON files from a specified directory, maps them to CanonicalQA objects using configurable column/key names.

## Key Components

* `LocalFileDownloader` class responsible for downloading seed files from the repo into a raw directory.
* `LocalFileParser` class responsible for parsing CSV and JSON files, yielding one dict per row or object.
* `LocalFileMapper` class responsible for mapping flat dictionaries (CSV rows/JSON objects) to CanonicalQA objects.

## Important Logic

* The module uses a configuration file to specify the column/key names for mapping.
* The `download()` method in `LocalFileDownloader` checks if seed files already exist in the raw directory and skips download if they do, unless forced by config.
* The `parse()` method in `LocalFileParser` yields one dict per row or object from CSV/JSON files, skipping rows based on config.
* The `map()` method in `LocalFileMapper` maps a flat dictionary to a CanonicalQA object using the column/key names specified in the config.

## Dependencies

* `csv` and `json` libraries for reading CSV and JSON files
* `shutil` library for copying seed files from repo to raw directory
* `logging` library for logging information and warnings
* Custom modules: `base`, `schema.canonical`, `schema.provenance`

## Notes

* The module assumes that the configuration file is in YAML format.
* The column/key names specified in the config should match the actual column names in the CSV/JSON files.
* The module uses UUIDs to generate unique identifiers for answers and questions.

---

