# Folder: stackexchange

## Overview

This folder contains the following files and their summaries.

## Files

### downloader.py

# File: downloader.py

## Purpose
Downloads per-site 7z archives from the Internet Archive mirror for Stack Exchange sites.

## Key Components
- `StackExchangeDownloader` class extends `AbstractDownloader`
- Downloads archives from specified sites in the `config` file
- Uses `httpx` library for streaming downloads

## Important Logic
- Iterates over specified sites and attempts to download each archive
- If an archive is already downloaded, skips it
- Streams the download using `httpx.stream` with chunking for progress logging

## Dependencies
- `httpx`
- `pathlib`

## Notes
- Designed for Stack Exchange sites
- Uses April 2024 snapshot from Internet Archive
- Logs progress and errors during downloads

---

### mapper.py

# File: mapper.py

## Purpose
Converts raw Stack Exchange post dicts into CanonicalQA records.

## Key Components
* `StackExchangeMapper`: a class that buffers answers and then emits questions.
* `_parse_tags` and `_parse_dt`: helper functions for parsing tags and dates from raw data.
* `_build_question`: a function that creates a CanonicalQA record from a question row and its answers.

## Important Logic
The mapper uses a two-pass strategy:
1. Buffer all answers keyed by ParentId (question ID).
2. Emit one CanonicalQA per question, attaching its answers.

## Dependencies
* `AbstractMapper` class from `..base`
* `CanonicalAnswer`, `CanonicalQA`, and `SourceName` classes from `...schema.canonical` and `...schema.provenance`

## Notes
The mapper is designed to handle large dumps by streaming data in batches. It uses UUIDs for canonical IDs and supports CC BY-SA 4.0 licenses.

---

### __init__.py

# File: __init__.py

## Purpose
Provides a Stack Exchange data source that enables downloading, parsing, and mapping of data.

## Key Components
- `StackExchangeSource` class, which inherits from `AbstractDataSource`
- Three child classes: `StackExchangeDownloader`, `StackExchangeParser`, and `StackExchangeMapper`

## Important Logic
- The `iter_canonical` method iterates over the canonical QA records in a two-pass process:
  1. Downloads raw files if not already downloaded.
  2. Parses the raw stream using `self._parser`.
  3. Maps the parsed stream to CanonicalQA objects using `self._mapper`.

## Dependencies
- `AbstractDataSource`, `AbstractDownloader`, `AbstractParser`, and `AbstractMapper` classes from parent modules
- `StackExchangeDownloader`, `StackExchangeParser`, and `StackExchangeMapper` child classes

## Notes
- Uses a two-pass approach to map answers to questions, requiring a custom iterator.
- Logs progress and errors during the data processing pipeline.

---

### parser.py

# File: parser.py

## Purpose
Extract posts, post links, and tags from 7z archives containing Stack Exchange XML data.

## Key Components
- `_parse_posts_xml`: Parse Posts.xml file and yield row dicts for questions and answers.
- `_parse_post_links_xml`: Parse PostLinks.xml (duplicate/related links between questions).
- `StackExchangeParser`: Class that parses all 7z archives in raw_dir and yields merged post dicts.

## Important Logic
- Archives are processed independently, and each site's archive is processed separately.
- Posts and post links are yielded as dicts with an extra `_site` key set to the archive's site name.
- PostLinks are yielded as dicts with `_record_type: "post_link"`.

## Dependencies
- `xml.etree.ElementTree`
- `py7zr` (for 7z archive handling)
- `logging`

## Notes
- The parser uses a SAX-style iterparse to handle low memory usage and streams rows as dicts.
- It can handle multiple sites' archives in parallel, yielding merged post dicts.

---

