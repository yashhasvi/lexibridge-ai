# Folder: wikidata

## Overview

This folder contains the following files and their summaries.

## Files

### __init__.py

# File: `__init__.py`

## Purpose
Expose Wikidata data to the graph store using the knowledge graph schema.

## Key Components
- `WikidataDownloader`: Downloads Wikidata JSON dump from Wikimedia.
- `WikidataTripleStream`: Streams and yields (Entity, Triple) pairs.
- `WikidataSource`: Adapter to expose Wikidata to SOURCE_REGISTRY/CLI commands.

## Important Logic
- The `WikidataTripleStream` class filters items based on config settings (e.g., min sitelinks, require English label).
- The `iter_entities_triples` method uses the `_stream` object to yield (Entity, Triple) pairs.
- The `WikidataSource` adapter sets up and returns an instance of `WikidataDownloader`, `_NoopParser`, and `_NoopMapper`.

## Dependencies
- Wikidata JSON dump from Wikimedia.
- `httpx` library for downloading the dump.

## Notes
- This module is part of a larger knowledge graph schema.
- The `iter_canonical()` method intentionally yields nothing, use `iter_entities_triples` instead.

---

