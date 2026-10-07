# Folder: graph

## Overview

This folder contains the following files and their summaries.

## Files

### __init__.py

# File: __init__.py

## Purpose
Initializes the data module's pipelines package.

## Key Components
- `TripleExtractor`: a class for extracting triples.
- `GraphBuilder`: a class for building graphs.

## Important Logic
None, this is an initialization file that only defines exports.

## Dependencies
- `.extractor` (Python module)
- `.builder` (Python module)

## Notes
This file defines what classes are exposed from the pipelines package.

---

### extractor.py

# File: extractor.py

## Purpose
This file contains a class `TripleExtractor` that extracts knowledge graph triples from CanonicalQA records.

## Key Components
* The `TripleExtractor` class has two main methods:
	+ `extract`: takes a single `CanonicalQA` record and returns a list of entities and a list of triples.
	+ `extract_stream`: takes an iterator of `CanonicalQA` records and yields tuples of lists of entities and triples for each record.
* The extractor uses the `_tid` function to generate unique IDs for triples.

## Important Logic
The extractor creates entities and triples based on the following criteria:
	+ Question entity node: creates a single question entity from the CanonicalQA record.
	+ Tag entities + TAGGED_WITH triples: creates one tag entity and one triple per tag in the record.
	+ DUPLICATE_OF triples: creates one triple for each duplicate of the current record found in the database.
	+ RELATED_TO triples: creates one triple for each related question found in the database.
	+ Answer entities + ANSWERS / ACCEPTED_FOR triples: creates one answer entity and two triples (ANSWERS and ACCEPTED_FOR) per answer in the record.
	+ Entity MENTIONS triples (from NER enrichment): creates one entity entity and one triple per mention of an entity found in the record.

## Dependencies
* `CanonicalQA`: a class representing a Canonical QA record.
* `Entity` and `Triple`: classes representing entities and triples in the knowledge graph.
* `PredicateType`, `SourceName`: constants or enumerations used to specify predicate types and source names.

## Notes
The extractor assumes that the input records have already been processed by some other component, and that the necessary data (e.g. tags, answers, entity mentions) is available for each record.

---

### builder.py

# File: builder.py

## Purpose
Builds a graph by extracting triples from a CanonicalQA stream and writing them to the graph store.

## Key Components
* `GraphBuilder` class responsible for building the graph.
* `TripleExtractor` used to extract triples from the CanonicalQA stream.
* `GraphStore` dependency for storing the extracted triples.
* Batch processing with configurable batch size.

## Important Logic
The `build` method processes the input records in batches, extracting entities and triples using the `TripleExtractor`. It periodically upserts these batches to the graph store. After processing all records, it flushes any remaining entities and triples.

## Dependencies
* `...schema.canonical.CanonicalQA`: input data schema.
* `...schema.graph.Entity` and `...schema.graph.Triple`: entity and triple data structures.
* `.extractor.TripleExtractor`: extractor for triples from CanonicalQA stream.
* `...storage.graph_store.GraphStore`: storage interface for graph data.

## Notes
The class uses a generator to process the input records in batches, making it efficient for large datasets. The batch size is configurable, allowing users to optimize performance based on their specific needs.

---

