# Folder: fetch

## Overview

This folder contains the following files and their summaries.

## Files

### agentic.py

# File: agentic.py

## Purpose
Agentic RAG fetcher is a tool-call-friendly multi-hop retrieval API designed to be used by an LLM agent. It allows for keyword + semantic searches, graph traversal, sub-question decomposition, and retrieval of subgraph context.

## Key Components
* `AgentContext`: Accumulates retrieved evidence across multiple agent tool calls.
* `AgenticFetcher`: Multi-tool fetcher that exposes discrete callable methods:
	+ `semantic_search`
	+ `keyword_search`
	+ `related_questions`
	+ `entity_context`
	+ `follow_duplicate`

## Important Logic
* The fetcher is initialized with three types of RAG fetchers: `FastRAGFetcher`, `GraphRAGFetcher`, and an optional `HybridFetcher`.
* Each tool method returns an updated `AgentContext` instance with the retrieved evidence.
* The `full_retrieval` method runs a complete retrieval pipeline in a single call.

## Dependencies
* `fast_rag`
* `graph_rag`
* `hybrid`

## Notes
* The code uses type hints and docstrings to provide clear documentation of the API.
* It is designed to be used as part of an LLM agent, with the fetcher methods serving as tools for the agent to use.

---

### hybrid.py

# File: hybrid.py

## Purpose
Hybrid fetcher that combines BM25 sparse retrieval and dense vector retrieval using Reciprocal Rank Fusion (RRF).

## Key Components
- `HybridFetcher` class, which extends the `AbstractFetcher` base class.
- `_rrf_score` function to calculate RRF score.
- `load_texts_from_parquet` method to build BM25 index from Parquet chunk archive.

## Important Logic
The hybrid fetcher uses two retrieval methods:
- Dense vector retrieval using `FastRAGFetcher`.
- Sparse BM25 retrieval with RRF fusion.
RRF combines the rankings from both retrievers without requiring score normalization.

## Dependencies
- `rank_bm25` library for BM25 retrieval.
- `fast_rag` module for dense vector retrieval.

## Notes
This implementation is designed for keyword-heavy technical queries and mixed-term semantic intent. The BM25 index is built lazily or pre-built via the `load_index()` method.

---

### fast_rag.py

# File: fast_rag.py

## Purpose
Fast RAG fetcher is a dense vector similarity search tool that uses LanceDB to find relevant chunks based on natural language queries.

## Key Components
- `FastRAGFetcher` class, which extends `AbstractFetcher`
- `_embedder` attribute, an embedder instance used for encoding queries and retrieving results
- `fetch` method, responsible for performing the similarity search

## Important Logic
The `fetch` method performs the following steps:
1. Encode the query with the same embedding model used during indexing.
2. Build a filter string based on optional scalar metadata filters (source, language, min score).
3. Search LanceDB using the encoded query and filter string.
4. Convert raw search results to `RetrievedChunk` objects.

## Dependencies
- `lance_store`: LanceStore instance for storing and retrieving data
- `embedding_model`: Embedding model used for encoding queries and retrieving results (default: "sentence-transformers/all-MiniLM-L6-v2")
- `device`: Device to use for embedding calculations (default: "cpu")

## Notes
The Fast RAG fetcher is optimized for high-throughput retrieval and suitable for single-hop factual questions, direct semantic similarity queries.

---

### __init__.py

# File: __init__.py

## Purpose
Provides a module for data retrieval using various fetcher classes.

## Key Components
* AbstractFetcher and RetrievedChunk base classes
* FastRAGFetcher, GraphRAGFetcher, HybridFetcher, and AgenticFetcher classes
* AgentContext class

## Important Logic
Exports the above-named classes to be used by other parts of the application.

## Dependencies
*.base (AbstractFetcher and RetrievedChunk)
*.fast_rag (FastRAGFetcher)
*.graph_rag (GraphRAGFetcher)
*.hybrid (HybridFetcher)
*.agentic (AgenticFetcher and AgentContext)

## Notes
This module serves as an entry point for the data retrieval functionality, making its classes accessible to other modules in the application.

---

### graph_rag.py

# File: graph_rag.py

## Purpose
Graph RAG fetcher — graph-augmented retrieval.

## Key Components
- Dense vector search using `FastRAGFetcher` to find seed chunks.
- Graph store (`GraphStore`) and LanceDB store (`LanceStore`) interactions.
- Subgraph expansion from the graph store based on parent question IDs.
- Fetching related questions, answers, and named entity context.

## Important Logic
1. Dense vector search to find seed chunks (fast_rag step).
2. Graph subgraph expansion: retrieve related questions and answers.
3. Fetch expanded question chunks from LanceDB.

## Dependencies
- `GraphStore` (`..storage.graph_store.AbstractStore`)
- `LanceStore` (`..storage.lance_store.LanceStore`)
- `FastRAGFetcher` (`.fast_rag.FastRAGFetcher`)

## Notes
This class is designed for multi-hop reasoning questions and related concepts. It uses a graph-augmented retrieval strategy to fetch richer context without an explicit multi-hop query.

---

### base.py

# File: base.py

## Purpose
Abstract interface for all retrieval backends, providing a common structure for fetching and returning data.

## Key Components
* `RetrievedChunk` class representing a single retrieval result with various attributes.
* `AbstractFetcher` abstract class defining the fetch method to retrieve results for a query string.

## Important Logic
* The `fetch` method in `AbstractFetcher` is an abstract method that must be implemented by concrete subclasses.
* The `RetrievedChunk` class has methods for formatting its contents as a context block suitable for LLM prompts.

## Dependencies
* `abc` module for abstract base classes and method definitions.
* `dataclasses` module for defining data classes with optional fields.
* `typing` module for type hints and annotations.

## Notes
* The file uses type hints and annotations to specify the expected types of variables and function parameters.
* The `RetrievedChunk` class has several attributes that can be modified, and some have default values or factory methods.

---

