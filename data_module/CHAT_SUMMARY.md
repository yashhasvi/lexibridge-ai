# Data Module — Chat Summary & Implementation Notes

> This file summarizes everything built in the initial implementation session.
> Use it to continue work in a new chat.

---

## What Was Built

A modular Python package at `/Users/ayush/Desktop/prj/data_module/` for:

- Ingesting QA data from 9 free/open sources
- Normalizing everything into a single `CanonicalQA` schema
- Storing data in backends optimized for each use case
- Retrieving data via fast dense search, graph-augmented RAG, hybrid BM25+dense, and agentic multi-tool APIs

Install with:

```bash
cd /Users/ayush/Desktop/prj/data_module
/Users/ayush/Desktop/prj/.venv/bin/pip install -e .
/Users/ayush/Desktop/prj/.venv/bin/python -m spacy download en_core_web_sm
```

---

## Data Sources

| # | Source | License | Access Method | What We Fetch |
|---|---|---|---|---|
| 1 | **Stack Exchange** (Apr 2024 Archive.org) | CC BY-SA 4.0 | `archive.org/details/stackexchange` (7z XML) | Questions, answers, tags, scores, accepted answer, post links |
| 2 | **Wikipedia** | CC BY-SA 4.0 + GFDL | HF `wikimedia/wikipedia` | Article text, abstracts |
| 3 | **Wikidata** | CC0 (fully unrestricted) | `dumps.wikimedia.org/wikidatawiki/entities` | Entity nodes, P31/P279 triples, labels |
| 4 | **SQuAD 2.0** | CC BY-SA 4.0 | HF `rajpurkar/squad_v2` | Reading comprehension QA + context paragraphs |
| 5 | **Natural Questions** | CC BY-SA 3.0 | HF `google-research-datasets/natural_questions` | Real Google queries + Wikipedia answers |
| 6 | **MS MARCO** | CC BY 4.0 | HF `microsoft/ms_marco` | Passage-level QA pairs, 1M+ queries |
| 7 | **HotpotQA** | CC BY-SA 4.0 | HF `hotpot_qa` | Multi-hop QA with supporting facts |
| 8 | **TriviaQA** | Apache 2.0 | HF `mandarjoshi/trivia_qa` | Trivia QA + Wikipedia evidence |
| 9 | **OpenAssistant OASST2** | Apache 2.0 | HF `OpenAssistant/oasst2` | Multi-turn conversation trees |

> **Yahoo CQA is NOT included** — only available via Yahoo WebScope (requires academic registration + non-commercial agreement).

### Stack Exchange Important Rule
**Do NOT use the profile-gated download at `stackoverflow.com/settings`.** Since July 2024 it requires agreeing to: *"I do not intend to use this file for training an LLM."* Use the **April 2024 Internet Archive mirror** instead — it predates the gate and the underlying CC BY-SA license permits all uses.

### Attribution Requirements (CC BY-SA)
All CC BY-SA sources require:
1. Attribution of original URL + author per record (stored in `source_url` field)
2. Derivative datasets must be released under CC BY-SA as well (share-alike)

---

## Complete File Tree

```
data_module/
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
│
├── config/
│   ├── sources/
│   │   ├── stackexchange.yaml
│   │   ├── wikipedia.yaml
│   │   ├── wikidata.yaml
│   │   ├── squad.yaml
│   │   ├── natural_questions.yaml
│   │   ├── ms_marco.yaml
│   │   ├── hotpotqa.yaml
│   │   ├── triviaqa.yaml
│   │   └── openassistant.yaml
│   ├── pipeline.yaml          ← chunk strategy, embedding model, NER, dedup settings
│   └── storage.yaml           ← DB paths, partition keys, backends
│
├── data_module/
│   ├── schema/                ← Pydantic models — source of truth for all records
│   │   ├── canonical.py       ← CanonicalQA, CanonicalAnswer, EntityMention
│   │   ├── chunk.py           ← ChunkRecord, ChunkMetadata
│   │   ├── graph.py           ← Triple, Entity, SubGraph
│   │   └── provenance.py      ← License, SourceName, ChunkType, PredicateType enums
│   │
│   ├── sources/               ← One sub-package per data source
│   │   ├── base.py            ← AbstractDataSource / Downloader / Parser / Mapper
│   │   ├── hf_base.py         ← Shared HuggingFace downloader + Parquet-cached parser
│   │   ├── stackexchange/     ← SAX XML parser + two-pass mapper (answer join)
│   │   ├── wikipedia/
│   │   ├── squad/
│   │   ├── natural_questions/
│   │   ├── ms_marco/
│   │   ├── hotpotqa/
│   │   ├── triviaqa/
│   │   ├── openassistant/     ← Two-pass tree mapper (message tree → Q+A)
│   │   └── wikidata/          ← Streams triples directly to graph store
│   │
│   ├── pipelines/             ← ETL stages
│   │   ├── orchestrator.py    ← Wires all stages end-to-end
│   │   ├── ingest/
│   │   │   ├── loader.py      ← Calls source.iter_canonical()
│   │   │   └── validator.py   ← SHA256 dedup via SQLite, min-length filter
│   │   ├── transform/
│   │   │   ├── normalizer.py  ← HTML strip (BeautifulSoup), unicode NFC
│   │   │   ├── deduplicator.py← Semantic near-dedup (optional, embedding-based)
│   │   │   └── enricher.py    ← spaCy NER → EntityMention objects
│   │   ├── chunk/
│   │   │   ├── strategies.py  ← 5 strategies (see below)
│   │   │   └── chunker.py     ← CanonicalQA → List[ChunkRecord]
│   │   ├── embed/
│   │   │   ├── embedder.py    ← Factory: sentence-transformers or OpenAI
│   │   │   └── batch.py       ← Batched embed with exponential-backoff retry
│   │   └── graph/
│   │       ├── extractor.py   ← CanonicalQA → List[Triple] + List[Entity]
│   │       └── builder.py     ← Bulk upsert triples to graph store
│   │
│   ├── storage/               ← Storage backend abstractions
│   │   ├── base.py            ← AbstractStore (context manager interface)
│   │   ├── parquet_store.py   ← Cold archive, partitioned by source+year
│   │   ├── duckdb_store.py    ← SQL analytics over Parquet (virtual views)
│   │   ├── lance_store.py     ← Hot ANN vector index (LanceDB)
│   │   ├── sqlite_store.py    ← Pipeline state, source_id→canonical_id mapping
│   │   └── graph_store.py     ← NetworkX (dev) / Neo4j (prod) + factory
│   │
│   ├── fetch/                 ← Retrieval APIs
│   │   ├── base.py            ← AbstractFetcher, RetrievedChunk dataclass
│   │   ├── fast_rag.py        ← Dense ANN via LanceDB + metadata filters
│   │   ├── graph_rag.py       ← Dense seed + 1-2 hop graph expansion
│   │   ├── hybrid.py          ← BM25 + dense with Reciprocal Rank Fusion
│   │   └── agentic.py         ← Multi-tool API with AgentContext accumulator
│   │
│   └── scripts/               ← CLI entry points (registered in pyproject.toml)
│       ├── download_sources.py← data-download <source>
│       ├── run_pipeline.py    ← data-pipeline run <source>
│       └── build_index.py     ← data-index build / stats
│
└── data/                      ← .gitignored
    ├── raw/                   ← Downloaded source files
    ├── processed/
    │   ├── canonical/         ← Parquet, partitioned by source+year
    │   └── chunks/            ← Parquet, partitioned by source+year
    └── index/
        ├── vectors/           ← LanceDB table files
        └── graph/             ← NetworkX .pkl.gz or Neo4j data
```

---

## Architecture: Data Flow

```
Raw XML/JSON/HF
      │
      ▼
Source Parser (per-source)
      │  CanonicalQA stream
      ▼
IngestValidator ──── SQLite (dedup by SHA256 content_hash)
      │
      ▼
Normalizer (HTML strip, unicode NFC)
      │
      ▼
Enricher (spaCy NER → EntityMention)
      │
      ├──────────────────────────────────────────────────────┐
      │                                                      │
      ▼                                                      ▼
Parquet Archive (cold)                            Triple Extractor
DuckDB views (analytics)                                    │
      │                                           Graph Store (NetworkX/Neo4j)
      ▼
Chunker (5 strategies)
      │  ChunkRecord stream
      ▼
BatchEmbedder (sentence-transformers / OpenAI)
      │  ChunkRecord + embedding
      ▼
Parquet chunks (cold)
LanceDB (hot ANN index)
```

---

## What Was Implemented (All Todos Completed)

### 1. Schema Layer (`data_module/schema/`)
- `CanonicalQA` — universal QA record with SHA256 `content_hash`, sorted answers, `attribution_str()`
- `CanonicalAnswer` — per-answer with `is_accepted`, `score`, `body_html`
- `EntityMention` — NER result with optional `wikidata_id`
- `ChunkRecord` — retrieval unit with fully denormalized `ChunkMetadata` (for filterless vector DB queries)
- `Triple` + `Entity` + `SubGraph` — knowledge graph primitives
- `License`, `SourceName`, `ChunkType`, `PredicateType` enums

### 2. Source Connectors (`data_module/sources/`)
Each source has three separated concerns:
- **Downloader** — fetches raw files (streaming HTTP, HF datasets library)
- **Parser** — reads raw files into dicts
- **Mapper** — converts raw dicts to `CanonicalQA`

Special handling:
- **Stack Exchange**: SAX iterparse (memory-efficient for 60M+ rows), two-pass mapper buffers answers by `ParentId` then joins to questions
- **OpenAssistant**: two-pass tree mapper groups messages by `message_tree_id`, reconstructs Q+A pairs with quality/toxicity filtering
- **Wikidata**: streams directly to graph store as `Triple` objects (no `CanonicalQA` needed)
- **HF sources**: all download via `datasets` library, cached as per-split Parquet for fast re-parsing

### 3. Ingest Pipeline (`data_module/pipelines/ingest/`)
- `loader.py` — source factory + `iter_canonical()` driver
- `validator.py` — `IngestValidator` with persistent SQLite dedup (survives restarts), min-length filter, tracks `source_id→canonical_id` mapping

### 4. Transform Pipeline (`data_module/pipelines/transform/`)
- `normalizer.py` — BeautifulSoup HTML strip, preserves code fences as backtick blocks, unicode NFC, whitespace collapse
- `deduplicator.py` — optional semantic near-dedup using cosine similarity rolling buffer (for post-processing; O(N²), use only on < 500k records)
- `enricher.py` — spaCy NER on title + first 500 chars, lazy model load, optional Wikidata entity linking

### 5. Chunking Strategies (`data_module/pipelines/chunk/`)
Five strategies in `strategies.py`:

| Strategy | Description | Best For |
|---|---|---|
| `canonical_qa` | Q title + body + best answer in one chunk | Default fast RAG |
| `per_answer` | One chunk per answer (with Q prefix) | Multi-answer threads |
| `question_only` | Question text only | Query-side indexing |
| `multi_hop` | Q + separate per-passage chunks with `parent_chunk_id` | HotpotQA, agentic reasoning |
| `hierarchical` | Q parent chunk + A child chunks linked via `parent_chunk_id` | Hierarchical retrieval |

`chunking_policy` name is stamped into `ChunkMetadata` for safe re-indexing.

### 6. Batched Embedder (`data_module/pipelines/embed/`)
- Pluggable via `get_embedder(model_name)` factory:
  - `sentence-transformers/all-MiniLM-L6-v2` (default, local, free)
  - `sentence-transformers/all-mpnet-base-v2` (better quality)
  - `text-embedding-3-small` (OpenAI, requires `OPENAI_API_KEY`)
- `BatchEmbedder` streams chunks in configurable batches (default 256)
- Exponential-backoff retry (3 attempts) on transient failures
- `embedding_model` + `embedding_dim` stamped into `ChunkMetadata` for version-safe reindex

### 7. Graph Extraction (`data_module/pipelines/graph/`)
`TripleExtractor` derives these edges from every `CanonicalQA`:

| Subject | Predicate | Object |
|---|---|---|
| Answer | `ANSWERS` | Question |
| Answer | `ACCEPTED_FOR` | Question (if `is_accepted`) |
| Question | `TAGGED_WITH` | Tag entity |
| Question | `DUPLICATE_OF` | Question |
| Question | `RELATED_TO` | Question |
| Question/Answer | `MENTIONS` | Named entity (from NER) |

`GraphBuilder` batches triple upserts (default batch 1000) into the graph store.

### 8. Storage Backends (`data_module/storage/`)

| Backend | File | Purpose |
|---|---|---|
| **Parquet** | `parquet_store.py` | Cold archive + training sets. Partitioned by `source` + `year`. zstd compression. |
| **DuckDB** | `duckdb_store.py` | Fast SQL over Parquet via virtual views. Built-in: `source_summary()`, `top_tags()`, `score_distribution()` |
| **LanceDB** | `lance_store.py` | Hot ANN vector index. Supports scalar filters, IVF-PQ index, cosine/L2/dot metric |
| **SQLite** | `sqlite_store.py` | Pipeline run history, `source_id→canonical_id` map, download status |
| **Graph** | `graph_store.py` | NetworkX (dev, gzip-pickled) or Neo4j (prod). `get_subgraph(entity_id, depth)` for Graph RAG |

`build_stores(storage_cfg, data_root)` factory constructs all five from the `config/storage.yaml`.

### 9. Retrieval APIs (`data_module/fetch/`)

**`FastRAGFetcher`** — pure dense retrieval via LanceDB ANN. Filters by `source`, `language`, `min_score`. Fastest path.

**`GraphRAGFetcher`** — dense seed search + graph expansion. For each seed, looks up `parent_question_id` in the graph, finds related questions via `RELATED_TO`/`DUPLICATE_OF` edges, fetches their chunks. Returns seeds + expanded context.

**`HybridFetcher`** — BM25 (`rank-bm25`) + dense fused via Reciprocal Rank Fusion (RRF). BM25 index built lazily from Parquet. Best for keyword-heavy technical queries.

**`AgenticFetcher`** — multi-tool API with `AgentContext` accumulator. Five discrete tools that LangChain/LlamaIndex can register:
1. `semantic_search(ctx, top_k)` — dense search
2. `keyword_search(ctx, top_k)` — BM25+dense hybrid
3. `graph_search(ctx, top_k, seed_k)` — graph-expanded dense search
4. `entity_context(ctx, entity_id, depth)` — adds subgraph text to context
5. `follow_duplicates(ctx, question_id)` — traverses `DUPLICATE_OF` edges

`AgentContext.to_prompt_context()` renders all accumulated evidence into a single LLM-ready string.

### 10. CLI Scripts (`data_module/scripts/`)

```bash
# Download raw source files
data-download stackexchange --sites stackoverflow unix
data-download squad
data-download all

# Run ETL pipeline
data-pipeline run squad --chunk-strategy canonical_qa
data-pipeline run stackexchange --limit 50000 --skip-embed
data-pipeline run all
data-pipeline status     # show run history from SQLite

# Build / inspect indexes
data-index build --source all
data-index stats         # LanceDB count, DuckDB source summary, graph node/edge counts
```

---

## Pending / What To Do Next

### Immediate (finish setup)

```bash
# Install all dependencies
cd /Users/ayush/Desktop/prj/data_module
/Users/ayush/Desktop/prj/.venv/bin/pip install -e .
/Users/ayush/Desktop/prj/.venv/bin/python -m spacy download en_core_web_sm

# Verify imports
/Users/ayush/Desktop/prj/.venv/bin/python -c "
from data_module.schema import CanonicalQA, ChunkRecord, Triple
from data_module.sources import SOURCE_REGISTRY
from data_module.pipelines.chunk.strategies import Strategy
print('OK — sources:', list(SOURCE_REGISTRY.keys()))
print('Strategies:', [s.value for s in Strategy])
"
```

### Start Ingesting Data (suggested order, smallest first)

```bash
# 1. SQuAD — fastest, ~50 MB, good for end-to-end smoke test
data-download squad
data-pipeline run squad --chunk-strategy canonical_qa

# 2. OpenAssistant OASST2 — ~200 MB, conversational variety
data-download openassistant
data-pipeline run openassistant

# 3. HotpotQA — multi-hop, tests multi_hop chunking
data-download hotpotqa
data-pipeline run hotpotqa --chunk-strategy multi_hop

# 4. TriviaQA / NQ / MS MARCO — medium size
data-download triviaqa
data-pipeline run triviaqa

# 5. Stack Exchange — large, run with limit first
data-download stackexchange --sites stackoverflow
data-pipeline run stackexchange --limit 100000 --chunk-strategy hierarchical

# 6. Wikipedia — very large, run last
data-download wikipedia
data-pipeline run wikipedia --skip-graph
```

### Build Indexes After Loading

```bash
data-index build --source all
data-index stats
```

### Potential Improvements to Add

- **Tests** — add `pytest` tests in a `tests/` directory (unit tests for mapper, chunker, validator)
- **Wikidata entity linking** — after loading Wikidata, build a label→Q-ID lookup dict and pass it to `Enricher(run_entity_linking=True, wikidata_index=...)`
- **Streaming orchestrator** — current orchestrator materializes all records into a list before chunking; replace with true streaming for large sources (Stack Exchange)
- **Prefect/Airflow integration** — `orchestrator.py` has hooks but no actual DAG wiring yet
- **BM25 index persistence** — `HybridFetcher` rebuilds BM25 from Parquet on each startup; add save/load to avoid rebuild
- **Chunking for Wikipedia** — Wikipedia articles are stored as single 4000-char chunks; add a sliding-window chunker for long articles
- **`data-pipeline run --resume`** — SQLite tracks `source_id→canonical_id` so resuming a partial run is possible; the CLI flag just isn't wired yet
