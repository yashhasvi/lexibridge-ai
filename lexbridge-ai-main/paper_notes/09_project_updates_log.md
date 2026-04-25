# 09 — Project Updates Log

> Purpose: short, dated changelog for implementation progress.
> Last updated: April 10, 2026

---

## 2026-04-10 (Current update)

### Tier 2 RAG Optimisations — Query Rewriting, Context Compression, Embedding Cache

**Motivation:** Tier 1 optimisations (BM25 default, reduced top-k, true streaming, latency metrics) were completed. Tier 2 targets retrieval quality, prompt efficiency, and embedding latency.

**1. Query Rewriting / Expansion** (`brain_module/query/rewriter.py`)

- Uses a fast LLM call (128 max tokens, temp=0.7) to generate 2 alternative phrasings of the user query.
- Original query always included as variant #1 — retrieval quality never degrades, variants only add recall.
- All variants run through `ParallelFetcher` in parallel via `asyncio.gather`, results merge into the same RRF aggregation.
- Resolves ambiguous pronoun references (e.g. "Who won it?" → "Who won the championship?").
- Config: `QUERY_REWRITE_ENABLED=true`, `QUERY_REWRITE_MAX_VARIANTS=3`.

**2. Context Compression** (`brain_module/compression/sentence_compressor.py`)

- After reranking, splits each chunk into sentences and scores them against the query via cosine similarity.
- Keeps only top-N sentences (default 5) per chunk above a minimum threshold (default 0.25).
- Preserves original sentence order within chunks for coherent reading.
- Purely extractive — no LLM call, uses the same sentence-transformers model already loaded.
- Integrated into `SynthesisEngine.synthesise()` and the `/ask/stream` path.
- Config: `CONTEXT_COMPRESSION_ENABLED=true`, `CONTEXT_COMPRESSION_MIN_SCORE=0.25`, `CONTEXT_COMPRESSION_TOP_SENTS=5`.

**3. Embedding Cache** (`brain_module/cache/embedding_cache.py`)

- LRU cache (OrderedDict, default 2048 entries) wrapping the embedder's `encode()` method.
- Mixed batch hits/misses handled correctly — only uncached texts hit the model.
- Wraps `FastRAGFetcher._embedder` at startup in `_register_data_module_fetchers`.
- Hit/miss stats available via `.stats` property for monitoring.
- Config: `EMBEDDING_CACHE_ENABLED=true`, `EMBEDDING_CACHE_MAXSIZE=2048`.

**Pipeline flow (updated):**
Route → Cache → **Query Rewrite** → Parallel Fetch (× variants, with **embedding cache**) → Aggregate → Rerank → Retrieval Guardrails → **Context Compression** → LLM Synthesis → Post-Generation Guardrails → Format + Cache

**Files added:**
- `brain_module/brain_module/query/__init__.py`
- `brain_module/brain_module/query/rewriter.py`
- `brain_module/brain_module/compression/__init__.py`
- `brain_module/brain_module/compression/sentence_compressor.py`
- `brain_module/brain_module/cache/embedding_cache.py`

**Files modified:**
- `brain_module/brain_module/api/main.py` — integrated all three, new env vars, updated pipeline steps.
- `brain_module/brain_module/synthesis/__init__.py` — context compressor in `SynthesisEngine`.

---

### LLM Response Guardrails — Multi-layer validation for RAG synthesis

**Motivation:** The pipeline produced contradictory/indirect answers for simple factual queries. Example: "What is the capital of Spain?" returned "Barcelona is not the capital of Spain..." — leading with a negation, discussing irrelevant sources about Catalonia and Venezuela, instead of simply answering "Madrid."

**Root causes identified:**
1. No minimum relevance cutoff on retrieved chunks — tangential sources (Barcelona, Venezuela) reached the LLM.
2. System prompt said "cite EVERY factual claim" — LLM dutifully discussed every source even if irrelevant.
3. No post-generation validation beyond citation index checks.
4. Streaming path (`/ask/stream`) had zero post-processing on the completed answer.
5. Rerank bypass for low-complexity factual queries meant cross-encoder scores weren't applied, defeating score-based filtering.

**New module: `brain_module/guardrails/`**

Four guardrail layers implemented:

**Layer 1 — Retrieval filtering** (`guardrails/retrieval_filter.py`):
- `filter_low_relevance()`: absolute score threshold (`MIN_RERANK_SCORE`, default 0.15).
- `filter_score_gap()`: relative filter — drops chunks scoring below 50% of the top chunk's score. Works regardless of score scale (raw RRF or cross-encoder sigmoid).
- `cap_source_diversity()`: limits chunks from the same source (`MAX_SAME_SOURCE`, default 2).

**Layer 2 — Prompt hardening** (`synthesis/prompt_builder.py`):
- Rewrote system prompt: "Answer DIRECTLY in your FIRST sentence", "Do NOT mention irrelevant sources — pretend they do not exist", "Keep answers SHORT for factual questions."
- Changed rule 1 from "cite EVERY factual claim" to "ONLY cite sources that directly answer the question."
- Added `factual` answer-type instruction: "Reply in 1-2 sentences MAX."
- Added `confidence_hint` parameter: injects low-relevance warning when avg reranker score is below `LOW_CONFIDENCE_THRESHOLD` (default 0.3).

**Layer 3 — Post-generation validation** (`guardrails/response_validator.py`):
- Negative-lead detector: flags answers starting with "X is not...", "No,", "That is incorrect" for factual queries.
- Self-contradiction scanner: regex patterns for "A is X... but A is not X".
- Answer-question alignment: keyword overlap between question and first sentence of answer.
- Confidence gate: appends disclaimer at low scores, replaces answer at very low scores.
- `ValidationResult` dataclass with `issues`, `suggested_action`, `modified_answer`.

**Layer 3b — Optional LLM-as-judge** (`guardrails/llm_judge.py`):
- Second-pass LLM call asks "does the answer directly address the question without contradiction?"
- Gated behind `ENABLE_LLM_JUDGE=false` (off by default). Fail-open on errors.

**Layer 4 — Streaming path parity** (`api/main.py` `/ask/stream`):
- Post-stream: citation validation + response validation on completed `full_answer`.
- `done` SSE event now includes `guardrail_flags` list and `cleaned_answer`.

**Schema changes:**
- `BrainResponse.guardrail_flags: list[str]` added (e.g. `["negative_lead", "low_alignment"]`).
- `ResponseFormatter.to_dict()` includes `guardrail_flags` in API output.

**Configuration (env vars):**
- `MIN_RERANK_SCORE` (default 0.15) — absolute score threshold.
- `MAX_SAME_SOURCE` (default 2) — max chunks per source in synthesis.
- `LOW_CONFIDENCE_THRESHOLD` (default 0.3) — triggers confidence hint in prompt.
- `ENABLE_LLM_JUDGE` (default false) — opt-in second-pass LLM validation.
- `GUARDRAIL_STRICT_MODE` (default false) — replace vs. disclaim on failures.

**Files added:**
- `brain_module/brain_module/guardrails/__init__.py`
- `brain_module/brain_module/guardrails/retrieval_filter.py`
- `brain_module/brain_module/guardrails/response_validator.py`
- `brain_module/brain_module/guardrails/llm_judge.py`

**Files modified:**
- `brain_module/brain_module/synthesis/prompt_builder.py` — rewritten system prompt + confidence_hint + factual instruction.
- `brain_module/brain_module/synthesis/__init__.py` — integrated all 3 retrieval filters, response validator, optional LLM judge.
- `brain_module/brain_module/api/main.py` — guardrail env vars in lifespan, streaming path parity, updated docstring.
- `brain_module/brain_module/response/schema.py` — `guardrail_flags` field on `BrainResponse`.
- `brain_module/brain_module/response/formatter.py` — `guardrail_flags` in JSON output.

---

## 2026-04-09

### Product / UX (brief)

- Upgraded the on-screen keyboard styling in the frontend for a more professional, modern feel:
  - Improved panel surface (depth, accent rail, refined header split).
  - Better keycap styling with clearer hover/active press feedback.
  - Higher visual hierarchy for modifier keys, Enter key, utility keys, and space bar.
- Added key-role theming via `react-simple-keyboard` `buttonTheme` mappings:
  - `pebble-key--mod` for `{shift}`, `{tab}`, `{lock}`, `{bksp}`
  - `pebble-key--accent` for `{enter}`
  - `pebble-key--space` for `{space}`
  - `pebble-key--utility` for `.com` and `@`

### Language support updates

- Removed **Tamil** from:
  - Speech language selector (`ta` option removed).
  - On-screen keyboard language selector (`tamil` layout removed).
- Existing saved keyboard language values in local storage now safely fall back to English if unsupported.

### Stability / verification

- Confirmed frontend build passes after updates (`tsc -b` + `vite build`).
- No new linter issues in touched frontend files.

---

## Notes for paper write-up

- These changes are primarily UX/input-surface improvements and do not alter retrieval methodology, evaluation protocol, or storage architecture.
- Keep frontend details concise in the paper; mention as usability/accessibility polish around multilingual input entry.

---

## Tier 3 RAG Production Optimisations

**Date**: 2026-04-10

### Motivation

After completing Tier 2 optimisations (query rewriting, context compression, embedding cache), three high-impact Tier 3 items were identified: HNSW index upgrade, tiered LLM routing, and semantic caching.

### 1. HNSW Index Support

**File**: `data_module/data_module/storage/lance_store.py`

Extended `LanceStore.create_index()` to support both IVF-PQ (original, compact) and HNSW-SQ (faster search, better recall). LanceDB 0.30+ supports `HnswSq` natively with m=16, ef_construction=150. Falls back to IVF-PQ on failure.

### 2. Tiered LLM Routing

**Files**: `brain_module/brain_module/synthesis/llm_client.py`, `brain_module/brain_module/api/main.py`

New `TieredLLMClient` routes simple queries (complexity < 0.35) to a fast small model and complex queries to the large model. Uses the existing `ComplexityScorer` output. Degrades gracefully to single-model when `LLM_MODEL_FAST` isn't configured.

**Verified results** (fast=gemma4:e4b, large=mistral):
- "What is a knowledge graph?" → complexity=0.12, intent=factual → **gemma4:e4b**
- Complex multi-hop comparison query → complexity=0.45, intent=multi_hop → **mistral**

**Config**:
```
LLM_MODEL_FAST=gemma4:e4b   # fast model for simple queries
LLM_TIERED_THRESHOLD=0.35   # complexity cutoff
```

### 3. Semantic Cache

**Files**: `brain_module/brain_module/cache/semantic_cache.py`, `brain_module/brain_module/api/main.py`

In-process embedding-similarity cache for near-duplicate queries. Embeds queries with sentence-transformers, does brute-force cosine scan against cached embeddings. Returns cached response if similarity >= 0.92. Sits between exact-match cache and the full pipeline.

**Verified results**:
- "What is retrieval augmented generation?" → full pipeline (17.7s)
- Same query → exact cache (4ms)
- "How does retrieval augmented generation work?" → semantic cache hit (8ms, sim=0.964)
- "What are knowledge graphs used for?" → correctly misses semantic cache, runs full pipeline

**Config**:
```
SEMANTIC_CACHE_ENABLED=true
SEMANTIC_CACHE_THRESHOLD=0.92
SEMANTIC_CACHE_MAXSIZE=1024
```

### Architecture Impact

The pipeline now has three cache layers checked in order:
1. **Exact-match** (SHA256 of normalised text) — <5ms
2. **Semantic cache** (cosine similarity ≥0.92) — ~8ms
3. **Full pipeline** (query rewrite → parallel fetch → aggregate → rerank → compress → synthesise) — 10-18s

The tiered LLM routing adds no latency overhead — it simply selects the appropriate client before the existing synthesis call.

### 4. vLLM / TGI Model Serving Support

**Files**: `brain_module/brain_module/synthesis/llm_client.py`, `brain_module/.env`

Added `VLLMClient` and `TGIClient` backends for production model serving. Both reuse the `OpenAIClient` since vLLM and TGI expose OpenAI-compatible APIs. The factory now accepts `"vllm"` and `"tgi"` as `LLM_BACKEND` values.

**Config** (commented out in `.env`, ready to activate):
```
LLM_BACKEND=vllm
LLM_MODEL=mistralai/Mistral-7B-Instruct-v0.3
VLLM_BASE_URL=http://localhost:8000/v1
```

Works with tiered routing — can use different backends per tier (e.g. `ollama` for fast, `vllm` for large).

### Deferred: Graph Neighborhood Precompute

Moved to dedicated plan: `neo4j_periodic_ingest_pipeline.plan.md`. Covers incremental graph ingest, periodic scheduling, neighborhood precomputation, entity summary caching, and stale data pruning.
