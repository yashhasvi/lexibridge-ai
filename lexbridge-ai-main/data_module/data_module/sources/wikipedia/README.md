# Folder: wikipedia

## Overview

This folder contains the following files and their summaries.

## Files

### __init__.py

# File: __init__.py

## Purpose
Provides a Wikipedia data source for text processing tasks.

## Key Components
- `WikipediaMapper`: Maps Wikipedia article rows to CanonicalQA objects.
- `WikipediaSource`: Downloads and prepares Wikipedia dataset using Hugging Face datasets library.

## Important Logic
- The `WikipediaMapper` class maps raw Wikipedia data to CanonicalQA format, including title, text, and answer processing.
- The `WikipediaSource` class downloads the Wikipedia dataset using the Hugging Face libraries and provides an interface for accessing it.

## Dependencies
- `datasets` library: For downloading Wikipedia dataset.
- `HFDownloader`, `HFParser`: Hugging Face libraries for downloading and parsing data.
- `AbstractMapper`, `AbstractDataSource`, `AbstractDownloader`, `AbstractParser`: Base classes for text processing tasks.

## Notes
This module uses the `datasets` library's wikipedia dataset as a fallback, with direct dump parsing via WikiExtractor available for full control.

---

