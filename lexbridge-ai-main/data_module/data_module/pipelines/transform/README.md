# Folder: transform

## Overview

This folder contains the following files and their summaries.

## Files

### deduplicator.py

# File: deduplicator.py

## Purpose
Remove duplicates from a stream of CanonicalQA records using semantic deduplication.

## Key Components
- `SemanticDeduplicator` class that uses embedding cosine similarity to remove near-duplicates.
- Rolling buffer of embeddings to store recent embeddings for comparison.
- Threshold value to determine when to skip a record based on its maximum cosine similarity to the buffer.

## Important Logic
- The `deduplicate` method iterates over a generator of CanonicalQA records, encoding each text using the provided embedder and comparing it against the rolling buffer of embeddings.
- If the maximum cosine similarity exceeds the threshold, the record is skipped and not yielded.

## Dependencies
- `numpy` library for numerical computations.
- `CanonicalQA` schema from parent module.

## Notes
- This implementation has a worst-case time complexity of O(N²) due to the matrix multiplication. Use approximate nearest-neighbour algorithms (e.g., LanceDB self-query) for large datasets instead.

---

### __init__.py

# File: __init__.py

## Purpose
Initializes the data module's pipelines for transformation.

## Key Components
- Normalization pipeline (Normalizer class)
- Deduplication pipeline (SemanticDeduplicator class)
- Enrichment pipeline (Enricher class)

## Important Logic
Exports the Normalizer, SemanticDeduplicator, and Enricher classes for use elsewhere in the module.

## Dependencies
None

## Notes
This is an initialization file that imports and exposes key data transformation classes.

---

### enricher.py

# File: enricher.py

## Purpose
Adds NER entity mentions to CanonicalQA records using spaCy and supports optional entity linking with Wikidata index.

## Key Components

*   `Enricher` class that adds entity mentions to CanonicalQA records
*   `enrich` method performs NER on title + body of a record and returns the enriched record
*   `enrich_stream` method enriches a stream of records using spaCy's batched nlp.pipe() for speed

## Important Logic

*   NER is performed on title + first 500 chars of body using spaCy model
*   Entity linking is optional and uses Wikidata index to match surface forms against entity labels and aliases
*   Enrichment is lazily loaded, meaning it only loads the necessary resources when needed

## Dependencies

*   `spacy` library for NER and entity linking
*   `logging` library for logging progress
*   `CanonicalQA` and `EntityMention` classes from `schema.canonical`

## Notes

*   Entity linking is disabled by default until the Wikidata index is built
*   The code uses spaCy's batched nlp.pipe() to speed up enrichment of large datasets
*   It supports multiprocessing for further speedup, but on macOS it's recommended to set `n_process=1`

---

### normalizer.py

# File: normalizer.py

## Purpose
Transform CanonicalQA records by stripping HTML and cleaning text.

## Key Components
- `_strip_html` function to remove HTML tags from input strings.
- `_normalize` function to normalize Unicode characters, whitespace, and code blocks in text.
- `Normalizer` class to apply normalization pipeline to a stream of CanonicalQA records.

## Important Logic
- The `normalize` method applies the normalization pipeline to each record in the input stream.
- If the cleaned text is too short (less than `min_text_length` characters), the original record is returned unchanged.
- The `normalize_stream` method yields new CanonicalQA objects with cleaned text, one at a time.

## Dependencies
- `CanonicalAnswer` and `CanonicalQA` schema classes from the parent package.
- `BeautifulSoup`, `MarkupResemblesLocatorWarning`, and other related modules from external libraries (e.g., `bs4`).

## Notes
- The normalizer operates in-place on input records, producing new immutable objects with cleaned text.
- The `log_every` parameter controls how frequently progress is logged during the normalization process.

---

