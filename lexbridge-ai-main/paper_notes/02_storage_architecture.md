# 02 — Storage Architecture

> This document covers the five-backend storage design: rationale for each backend, trade-offs, and how they interoperate.

---

## Design Philosophy

The central insight is that **no single storage system optimally serves all access patterns** for a production Q&A pipeline. A vector database is excellent for ANN search but terrible for SQL analytics. A graph database is excellent for relationship traversal but terrible for embedding lookup. We designed a five-backend architecture where each backend handles exactly the access pattern it was built for.

This is similar to how production data systems separate OLTP (operational), OLAP (analytical), and search workloads — except here we also add vector and graph dimensions.

---

## The Five Backends

### 1. Parquet — Cold Archive

| Property | Value |
|---|---|
| Library | `pyarrow` |
| Format | Parquet, partitioned by `source` + `year` |
| Compression | zstd |
| Access pattern | Batch read for analytics, training set export |
| Latency | High (seconds to minutes for full scans) |
| Purpose | Cold storage, training data, audit trail |

**Why Parquet:**
Parquet is the de facto standard for large-scale tabular data in the ML/data engineering ecosystem. zstd compression achieves 3–5x size reduction over raw JSON while remaining columnar (column-pruning means you only read the columns you need). Partitioning by source + year allows efficient filtering without full scans.

**What is stored:**
- All `CanonicalQA` records after normalisation
- All `ChunkRecord` records after chunking and embedding

**Role in the system:**
- Primary source of truth — if any downstream index is corrupted or needs rebuilding, Parquet is the ground truth
- Training set export for fine-tuning experiments
- DuckDB virtualises over Parquet for SQL analytics (see below)

**Trade-offs:**
- Not suitable for point lookups by `canonical_id` — use SQLite for that
- Not suitable for ANN search — use LanceDB for that
- Not suitable for graph traversal — use Neo4j for that

---

### 2. DuckDB — SQL Analytics

| Property | Value |
|---|---|
| Library | `duckdb` |
| Format | Virtual views over Parquet files |
| Access pattern | Analytical SQL queries |
| Latency | Low-to-medium (100ms–5s for complex aggregations) |
| Purpose | Exploration, monitoring, ad-hoc analysis |

**Why DuckDB:**
DuckDB is an in-process OLAP database that can query Parquet files directly as virtual tables — no data copying required. It is far faster than pandas for analytical workloads (vectorised execution, parallel query) and requires no server setup.

**Built-in views and queries:**
```sql
-- Source distribution summary
source_summary()  →  SELECT source, COUNT(*), AVG(answer_count), SUM(answer_count) FROM canonical GROUP BY source

-- Top tags across all sources
top_tags(n=20)  →  SELECT tag, COUNT(*) FROM exploded_tags GROUP BY tag ORDER BY COUNT(*) DESC LIMIT n

-- Score distribution
score_distribution(source)  →  histogram of answer scores
```

**Role in the system:**
- Monitoring: track ingestion progress, source sizes, tag distributions
- Evaluation: compute aggregate metrics (e.g. average answer count by source)
- Debug: identify data quality issues (empty bodies, missing tags)
- Paper: generate dataset statistics tables directly from SQL

**Trade-offs:**
- Read-only (writes go to Parquet first)
- Not suitable for real-time query serving

---

### 3. LanceDB — Hot Vector Index

| Property | Value |
|---|---|
| Library | `lancedb` |
| Format | IVF-PQ compressed vector index + payload |
| Index type | IVF-PQ (Inverted File Index with Product Quantisation) |
| Metrics | Cosine, L2, Dot product (configurable) |
| Access pattern | ANN search with optional scalar metadata filters |
| Latency | Very low (<10ms for ANN queries) |
| Purpose | Dense semantic retrieval in production |

**Why LanceDB over FAISS or Pinecone:**
- **vs FAISS**: LanceDB persists to disk natively (FAISS requires manual save/load), supports metadata filters alongside ANN (FAISS does not), and has a Python-native API. FAISS is appropriate for research experiments; LanceDB is appropriate for production systems.
- **vs Pinecone/Weaviate**: LanceDB is fully local and open-source — no API key, no cost, no network latency. For a research project with large data volumes, this is decisive.
- **vs Chroma**: LanceDB has better performance at scale and first-class Parquet integration.

**What is stored:**
- `ChunkRecord` objects with their embedding vectors
- Fully denormalised `ChunkMetadata` (source, source_url, tags, score, language, chunk_type, embedding_model) — denormalisation is intentional to enable metadata filtering without joins

**Scalar filters supported:**
```python
# Filter by source + language without touching the vector index
results = lance_store.search(
    query_vector=embed("async python"),
    filters={"source": "stackexchange", "language": "en", "min_score": 10}
)
```

**IVF-PQ index:**
Product Quantisation compresses 768-dim float32 vectors (3072 bytes each) down to ~96 bytes (32x compression) with minimal recall degradation. At 10M+ vectors, this is the difference between a 30GB and a 1GB index.

**Trade-offs:**
- Approximate (not exact) nearest neighbour — there is a recall/speed trade-off governed by the `nprobe` parameter
- Does not support graph traversal

---

### 4. SQLite — Pipeline State

| Property | Value |
|---|---|
| Library | `sqlite3` (stdlib) |
| Access pattern | Point lookups, small range scans |
| Latency | Very low (<1ms) |
| Purpose | Operational metadata, dedup tracking, pipeline state |

**Why SQLite:**
SQLite is the right tool for structured operational metadata that needs ACID guarantees, transactional writes, and point lookups. It is embedded (no server), zero-config, and universally available.

**What is stored:**
- `ingested` table: `(canonical_id, source, source_id, content_hash, ingested_at)` — the deduplication registry
- `pipeline_runs` table: `(run_id, source, stage, status, records_processed, started_at, finished_at)`
- `source_id_map` table: `(source, source_id, canonical_id)` — enables looking up a CanonicalQA by its original source ID

**Critical role — crash-safe dedup:**
The `content_hash` in SQLite is checked before writing any record to Parquet or LanceDB. This means the pipeline can be interrupted and restarted without producing duplicate records — a critical property when ingesting 60M+ Stack Exchange posts over hours or days.

**Trade-offs:**
- Single-writer (WAL mode supports concurrent readers, but only one writer at a time)
- Not suitable for large-scale analytics — that's DuckDB's job

---

### 5. Graph Store — NetworkX (dev) / Neo4j (prod)

| Property | Value |
|---|---|
| Libraries | `networkx` (dev), `neo4j` Python driver (prod) |
| Format | Directed labelled property graph |
| Access pattern | Subgraph queries, 1–2 hop traversal, entity neighbourhood |
| Latency | Low (Neo4j: <50ms for typical subgraph queries) |
| Purpose | Knowledge graph for graph-augmented retrieval |

**Why a graph store:**
Certain questions require reasoning over **relationships** between entities, not just semantic similarity between passages. Examples:
- "What tags are most related to the accepted answer for this question?"
- "Which Stack Overflow questions are duplicates of this one?"
- "What Wikipedia articles mention the same entities as this HotpotQA passage?"

A graph naturally models these relationships; a vector index cannot.

**Graph schema:**

Nodes:
- `Question (canonical_id, source, title, tags)`
- `Answer (canonical_id, score, is_accepted)`
- `Entity (entity_id, label, wikidata_id?)`
- `Tag (name)`

Edges (directed):
| Edge type | From | To | Meaning |
|---|---|---|---|
| `ANSWERS` | Answer | Question | Answer is a response to Question |
| `ACCEPTED_FOR` | Answer | Question | Answer is the accepted answer |
| `TAGGED_WITH` | Question | Tag | Question has this tag |
| `DUPLICATE_OF` | Question | Question | Stack Exchange duplicate link |
| `RELATED_TO` | Question | Question | Stack Exchange related link |
| `MENTIONS` | Question/Answer | Entity | NER-detected entity mention |

**NetworkX vs Neo4j:**
- NetworkX: stored as gzip-pickled `.pkl.gz`. Fast for dev/research, supports any Python graph algorithm, but: single-process, not persistent across memory, no Cypher query language.
- Neo4j: full graph database with Cypher query language, persistent storage, bolt protocol for concurrent access, and LightRAG's native graph backend. Required for production.

**`get_subgraph(entity_id, depth)` API:**
The key retrieval method — given an entity (or question) ID, returns all nodes within `depth` hops, which is then converted to text chunks for LLM context.

**Trade-offs:**
- Graph construction requires NER pipeline to have run (entity extraction)
- Wikidata entity linking is not yet complete (EntityMention → Wikidata Q-ID gap)
- NetworkX is not suitable for parallel access in production

---

## How the Five Backends Interoperate

```
CanonicalQA record created
         │
         ├─► SQLite: check content_hash → skip if duplicate
         │         write source_id_map entry
         │
         ├─► Parquet: write to cold archive (partitioned)
         │
         ├─► DuckDB: automatic (virtual view over Parquet, no write needed)
         │
         ├─► Chunker → ChunkRecord with embedding
         │       │
         │       └─► LanceDB: write vector + metadata
         │
         └─► Triple Extractor → List[Triple]
                 │
                 └─► Graph Store (NetworkX/Neo4j): upsert triples
```

---

## Paper Notes: What to Highlight

- The five-backend design is a deliberate separation of concerns, not over-engineering. Each backend handles a different access pattern at its native performance level.
- The `content_hash`-based deduplication in SQLite is the key to making incremental ingestion reliable — this is not a commonly documented pattern in RAG system papers.
- The fully denormalised `ChunkMetadata` in LanceDB (all fields duplicated at the chunk level) is a deliberate trade-off: it wastes storage space but eliminates join latency at query time — critical for <10ms retrieval.
- The `chunking_policy` field in `ChunkMetadata` means indexes can be rebuilt with a different strategy without data corruption — each index version is identified by its policy name.
- Future work: replace NetworkX with Neo4j in all environments, complete Wikidata entity linking, add BM25 index persistence (currently rebuilt from Parquet on every startup).
