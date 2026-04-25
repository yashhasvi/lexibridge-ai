# 03 — Retrieval Strategies

> This document covers the four retrieval strategies implemented in `data_module/fetch/`, their design rationale, strengths/weaknesses, and how they are combined via Reciprocal Rank Fusion.

---

## Why Multiple Retrieval Strategies?

No single retrieval strategy dominates across all query types. This is an empirically established fact in information retrieval:

| Query type | Best strategy | Why |
|---|---|---|
| Semantic/conceptual ("explain async I/O") | Dense ANN | Captures meaning, not just keywords |
| Keyword/technical ("AttributeError NoneType") | BM25 | Exact token match matters more than semantics |
| Multi-hop ("library used by framework that X uses") | Graph traversal | Requires following entity relationships |
| Broad thematic ("common patterns in Python async") | LightRAG global | KG community summaries capture themes |
| Mixed | Hybrid (BM25 + dense) | Hedges between both failure modes |

The system implements all four — and in the brain module they are run **in parallel** and fused, rather than choosing one.

---

## Chunking Strategies (Prerequisites for Retrieval)

Before retrieval can happen, `CanonicalQA` records are split into `ChunkRecord` objects. Five strategies are implemented:

| Strategy | Description | Chunk content | Best for |
|---|---|---|---|
| `canonical_qa` | Q title + body + best answer in one chunk | Everything in one | Default, fast RAG |
| `per_answer` | One chunk per answer (with Q title prefix) | Single answer + Q title | Multi-answer threads |
| `question_only` | Question text only | Question | Query-side indexing |
| `multi_hop` | Q + separate per-passage chunks | Each supporting passage | HotpotQA, multi-hop |
| `hierarchical` | Q as parent chunk, each A as child | Parent-child linked | Stack Exchange threads |

The `chunking_policy` field is stamped into `ChunkMetadata` at index time. This allows safe re-indexing with a different strategy — old and new strategy indexes coexist, keyed by policy name.

**Key design note:** `ChunkMetadata` is **fully denormalised** — all metadata fields are duplicated at the chunk level. This prevents join latency at query time. The trade-off is storage cost (roughly 2–3x larger LanceDB index), which is acceptable given retrieval is latency-sensitive.

---

## Strategy 1: FastRAGFetcher — Dense ANN

**File:** `data_module/fetch/fast_rag.py`

### What it does
Encodes the query into a dense vector using the same embedding model used at index time, then performs ANN search against LanceDB.

### Algorithm
```
query_text → embedding_model → query_vector (768-dim)
query_vector + filters → LanceDB.search(top_k, filters)
→ List[RetrievedChunk] sorted by cosine similarity
```

### Filters supported
- `source`: restrict to specific source(s) (e.g. only `stackexchange`)
- `language`: restrict to language code (e.g. `en`)
- `min_score`: minimum answer score (for Stack Exchange quality filtering)
- `chunk_type`: restrict to specific chunk type (e.g. `canonical_qa` only)

### Strengths
- Extremely fast (<10ms for ANN query)
- Captures semantic similarity — finds relevant passages even when keywords differ
- Works well for conceptual questions

### Weaknesses
- Fails on rare/specific keywords — the embedding model averages out uncommon tokens
- Cannot follow relationships — "the library used by X" type queries require graph traversal
- Susceptible to popularity bias — common topics overwhelm rare-but-relevant passages

### When the QueryRouter sends queries here
- Simple factual questions
- Conceptual / explanation queries
- Low-complexity queries where graph traversal is overkill

---

## Strategy 2: GraphRAGFetcher — Knowledge Graph Expansion

**File:** `data_module/fetch/graph_rag.py`

### What it does
Performs a dense seed search (same as FastRAG) to find initial candidate chunks, then uses the knowledge graph to expand context by following edges.

### Algorithm
```
query → dense seed search → top-k seed chunks
for each seed chunk:
    look up question_id in graph store
    find neighbours via RELATED_TO / DUPLICATE_OF / TAGGED_WITH / MENTIONS edges
    fetch chunks for neighbour nodes
→ seeds + expanded neighbours, deduplicated
```

### Graph edges used for expansion
- `RELATED_TO`: Stack Exchange "linked questions" — questions the community considered related
- `DUPLICATE_OF`: Stack Exchange duplicate markers — the canonical answer to a duplicated question
- `MENTIONS`: Questions that mention the same named entities (from NER)
- `TAGGED_WITH → TAGGED_WITH`: questions sharing the same tag cluster

### Strengths
- Retrieves passages that are *semantically distant* but *relationally close* — catches answers the dense search would miss
- `DUPLICATE_OF` traversal is particularly powerful: the best answer to the canonical question is retrieved even when the user phrased the question differently
- Entity-based expansion (via `MENTIONS`) links passages across different sources (e.g. a Wikipedia article and a Stack Overflow answer that both mention the same entity)

### Weaknesses
- Slower than FastRAG — graph traversal adds 50–200ms
- Quality depends on graph completeness (NER coverage, Wikidata linking)
- Can introduce irrelevant passages if graph edges are noisy

### When the QueryRouter sends queries here
- Queries containing named entities (detected by the router's NER check)
- Queries that appear to involve relationships ("related to", "used by", "built on")
- Medium-complexity queries where graph expansion is likely to help

---

## Strategy 3: HybridFetcher — BM25 + Dense (RRF)

**File:** `data_module/fetch/hybrid.py`

### What it does
Runs BM25 (lexical/keyword) retrieval and dense retrieval independently, then fuses their result lists using Reciprocal Rank Fusion.

### Algorithm
```
BM25 index (built lazily from Parquet)
query_text → BM25.get_scores() → ranked list A

query_text → embedding → ANN search → ranked list B

RRF(A, B) = for each doc d: score(d) = Σ 1/(60 + rank_i(d))
→ sorted by RRF score → top_k
```

**RRF constant k=60:** This is the standard value from Cormack et al. (2009). It controls the relative weight of high-ranked vs low-ranked documents. Higher k makes the fusion more uniform; lower k gives more weight to top-ranked documents.

### BM25 implementation
Uses `rank-bm25` library (`BM25Okapi`). The BM25 index is built lazily from Parquet on first query and cached in memory. This avoids slow startup but means the first query after a restart pays the build cost (~5–30 seconds depending on corpus size).

**Future work:** Persist the BM25 index to disk (pickle) to avoid rebuild on restart.

### When BM25 outperforms dense retrieval
- Error messages: `AttributeError: 'NoneType' object has no attribute 'strip'` — the exact error string matters
- Version-specific queries: `numpy 1.24 deprecation warning` — exact version number is critical
- Code patterns: `for key, value in dict.items()` — exact syntax matching
- Rare/specialised terminology: `SIGBUS`, `ENOMEM`, `POSIX semaphore` — uncommon tokens

### When dense retrieval outperforms BM25
- Paraphrase queries: "how do I copy a file in Python" vs chunks containing "file duplication", "shutil", "file transfer"
- Conceptual queries: "explain the difference between threads and processes"
- Cross-lingual adjacent queries (where vocabulary differs but meaning is close)

### Strengths
- Combines best of both worlds: semantic coverage (dense) + keyword precision (BM25)
- RRF is parameter-free after k is set — no score normalisation needed
- Particularly strong on technical/programming queries

### Weaknesses
- Slower than FastRAG (BM25 index rebuild on startup)
- Still cannot follow graph relationships
- BM25 index lives in memory — large corpora require significant RAM

---

## Strategy 4: AgenticFetcher — Multi-Tool Accumulator

**File:** `data_module/fetch/agentic.py`

### What it does
Exposes all retrieval capabilities as discrete tool-calling functions that an LLM agent (LangChain, LlamaIndex, or direct function calling) can invoke iteratively. Rather than a single-pass retrieval, the agent decides which tools to call and accumulates context across multiple calls.

### Tools exposed
```python
1. semantic_search(ctx, query, top_k)      → dense ANN
2. keyword_search(ctx, query, top_k)       → BM25 + dense hybrid
3. graph_search(ctx, query, top_k)         → graph-expanded dense
4. entity_context(ctx, entity_id, depth)   → subgraph text
5. follow_duplicates(ctx, question_id)     → DUPLICATE_OF traversal
```

### AgentContext accumulator
All tool calls accumulate into an `AgentContext` object:
```python
ctx = AgentContext(query="...")
await fetcher.semantic_search(ctx, top_k=5)
await fetcher.graph_search(ctx, top_k=3)
await fetcher.entity_context(ctx, entity_id="Python_GIL", depth=2)

prompt_context = ctx.to_prompt_context()
# → "Source 1 (Stack Overflow, score=0.94): ...\nSource 2 (Wikipedia, score=0.87): ..."
```

### When to use
- Complex multi-step reasoning queries
- When the agent needs to iteratively refine context (e.g. first retrieve, notice a gap, retrieve again)
- Research/exploration queries where the right retrieval strategy is not known upfront

### Strengths
- Most flexible — the agent can adapt the retrieval strategy based on intermediate results
- Enables multi-step reasoning chains

### Weaknesses
- Highest latency (multiple sequential LLM + retrieval calls)
- Requires an LLM agent orchestrator
- Not suitable for latency-sensitive production serving

---

## Reciprocal Rank Fusion (RRF) — The Fusion Algorithm

RRF is used in two places:
1. Inside `HybridFetcher` (BM25 + dense)
2. In the brain module's `MultiSourceAggregator` (fusing all fetcher outputs)

### Formula
For a set of ranked lists `{R_1, R_2, ..., R_n}` and a document `d`:

```
RRF_score(d) = Σ_{i=1}^{n} 1 / (k + rank_i(d))
```

Where:
- `k = 60` (standard value, Cormack et al. 2009)
- `rank_i(d)` is the position of document `d` in list `R_i` (1-indexed)
- If `d` does not appear in list `R_i`, it contributes 0

### Why RRF over score normalisation
Score normalisation (e.g. min-max scaling cosine scores) requires assuming scores are on comparable scales. BM25 scores and cosine similarities are not comparable — normalising them introduces arbitrary bias.

RRF avoids this entirely by converting to rank positions, which are always comparable. A document ranked #3 by BM25 and #2 by dense gets a high RRF score regardless of the absolute scores.

### Empirical properties
- **Robust**: adding a low-quality retriever rarely hurts (low-quality results rank low → small RRF contribution)
- **No training needed**: no learned weights required
- **Handles missing documents gracefully**: a document not retrieved by one system simply contributes 0 from that system

---

## Embedding Models

All dense retrieval paths share the same embedding model, configurable via `config/pipeline.yaml`:

| Model | Dim | Notes |
|---|---|---|
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | Default, fast, free, local |
| `sentence-transformers/all-mpnet-base-v2` | 768 | Better quality, still local |
| `text-embedding-3-small` (OpenAI) | 1536 | Best quality, requires API key |
| `BAAI/bge-m3` | 1024 | Recommended for production: multilingual, state-of-art |

**Critical constraint:** The embedding model is stamped into `ChunkMetadata.embedding_model`. Changing the model requires rebuilding the LanceDB index from Parquet. The Parquet cold store is the ground truth that makes this safe to do.

---

## Paper Notes: What to Highlight

- The decision to implement four separate retrieval strategies (rather than picking one) is grounded in the empirical observation that no single strategy dominates across all query types — this should be validated experimentally in the evaluation section
- The fully denormalised `ChunkMetadata` design is an explicit trade-off between storage cost and query latency — state this explicitly
- BM25 index persistence (currently missing) is a known limitation that affects startup time for the hybrid fetcher
- The `AgenticFetcher` is architecturally aligned with the "tool-calling" paradigm in modern LLM frameworks (LangChain, LlamaIndex, OpenAI function calling) — this is a forward-looking design decision worth noting
- RRF citation: Cormack, G.V., Clarke, C.L.A., Buettcher, S. (2009). *Reciprocal Rank Fusion outperforms Condorcet and individual rank learning methods.* SIGIR 2009.
