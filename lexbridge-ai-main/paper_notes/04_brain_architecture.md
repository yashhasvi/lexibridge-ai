# 04 — Brain Module Architecture

> This document covers the full design of the brain module: the reasoning, synthesis, and multi-source presentation layer that sits on top of the data module's retrieval APIs.

---

## Problem Statement (Reiterated)

The `data_module/fetch/` APIs return ranked lists of `RetrievedChunk` objects — raw text passages with metadata. The brain module answers the question: **"Given a user's question, how do we go from raw retrieved chunks to a trustworthy, cited, multi-source answer?"**

This requires:
1. Deciding *which* retrieval strategies to activate (not all queries need all strategies)
2. Running retrieval *in parallel* across the activated strategies
3. *Fusing* the results across strategies without score incompatibilities
4. *Re-ranking* the fused candidates with a more accurate (but slower) model
5. *Synthesising* a coherent answer from the top candidates using an LLM
6. *Attributing* every claim in the answer back to its source
7. *Formatting* the result as a structured, frontend-ready response

---

## Module Structure

```
brain_module/
├── router/
│   ├── intent_classifier.py   # query type: factual/multi-hop/technical/unanswerable
│   └── complexity_scorer.py   # decides which fetchers to activate
├── retrieval/
│   ├── lightrag_adapter.py    # CanonicalQA → LightRAG + query bridge
│   ├── fetcher_registry.py    # wraps all 4 existing fetchers + LightRAG
│   └── parallel_runner.py     # asyncio.gather across active fetchers
├── aggregation/
│   ├── deduplicator.py        # hash + semantic dedup across fetcher results
│   ├── source_grouper.py      # group by source_name for presentation
│   └── rrf_merger.py          # RRF fusion across fetcher result lists
├── reranking/
│   └── cross_encoder.py       # BAAI/bge-reranker-v2-m3 or ms-marco-MiniLM-L-6-v2
├── guardrails/                # multi-layer validation (added 2026-04-10)
│   ├── retrieval_filter.py    # min-score, score-gap, source-diversity filters
│   ├── response_validator.py  # contradiction/negative-lead/alignment heuristics
│   └── llm_judge.py           # optional LLM-as-judge second-pass (off by default)
├── synthesis/
│   ├── prompt_builder.py      # constructs multi-source citation prompt
│   ├── llm_client.py          # OpenAI / Ollama / vLLM / TGI / LiteLLM / TieredLLMClient factory
│   └── citation_parser.py     # maps [1][2][3] → SourceCard objects
├── query/
│   └── rewriter.py            # LLM-based query expansion (2-3 variants)
├── compression/
│   └── sentence_compressor.py # extractive sentence-level context compression
├── response/
│   ├── schema.py              # BrainResponse, SourceCard dataclasses
│   └── formatter.py           # JSON + markdown + human-readable
├── evaluation/
│   └── ragas_eval.py          # Ragas metrics on every response
├── cache/
│   ├── query_cache.py         # Redis or lru_cache for exact query→response
│   ├── embedding_cache.py     # LRU cache for query embedding vectors
│   └── semantic_cache.py      # embedding-similarity cache for near-duplicate queries
└── api/
    └── main.py                # FastAPI: /ask, /ask/stream, /health
```

---

## Component 1: QueryRouter

**Purpose:** Classify the query and decide which fetchers to activate, avoiding unnecessary latency from running all 4–5 fetchers on every query.

### Intent classification

| Intent class | Description | Fetchers activated |
|---|---|---|
| `factual_simple` | Direct factual lookup ("Who invented X") | FastRAG only |
| `technical_keyword` | Error messages, version-specific, code syntax | HybridFetcher (BM25 prioritised) |
| `conceptual` | Explanations, definitions, comparisons | FastRAG + LightRAG local mode |
| `multi_hop` | Requires chaining across entities/passages | GraphRAG + LightRAG hybrid |
| `thematic_broad` | "What are common patterns in X" | LightRAG global mode |
| `unanswerable` | Detected as out-of-scope or too vague | Return clarification prompt |

### Complexity scoring

A simple rule-based + embedding-based complexity score (0.0–1.0):

- Named entity count (via spaCy): higher count → higher complexity
- Sentence count: multi-sentence queries → higher complexity
- Presence of multi-hop keywords: "used by", "built on", "related to", "compared to" → boost
- Presence of error patterns (`Error:`, traceback markers) → route to BM25

### Design decision: Why not let the LLM decide?

An LLM could classify the query, but this adds 1–3 seconds of latency **before retrieval even starts**. The QueryRouter is intentionally a cheap (<5ms) classifier. Misclassification cost is low: a "multi_hop" query routed to FastRAG may get a slightly worse answer, but not a wrong one.

---

## Component 2: LightRAG Adapter

**Purpose:** Bridge between the existing data module's ingested data and LightRAG's internal representation.

### Why LightRAG is needed

LightRAG (Guo et al., arXiv:2410.05779) provides Knowledge Graph-augmented retrieval with two complementary modes:

- **Local mode**: Query is decomposed into entity mentions → entities are retrieved from the KG → their immediate neighbourhood (1-2 hops) provides context. Best for specific entity-centric questions.
- **Global mode**: High-level KG community summaries (computed offline by the Leiden algorithm) answer broad thematic questions. Best for "what are common approaches to X" type queries.
- **Hybrid mode**: Both modes run in parallel and results are merged.

This is qualitatively different from the existing `GraphRAGFetcher` — LightRAG builds community-level abstractions, not just per-entity neighbourhoods.

### Ingestion adapter

```python
# For each CanonicalQA record, construct a text document for LightRAG's insert()
def canonical_qa_to_lightrag_text(qa: CanonicalQA) -> str:
    parts = [f"Question: {qa.title}"]
    if qa.body_markdown:
        parts.append(f"Details: {qa.body_markdown[:500]}")
    if qa.answers:
        best = qa.answers[0]
        parts.append(f"Answer: {best.body_markdown[:800]}")
    if qa.tags:
        parts.append(f"Tags: {', '.join(qa.tags)}")
    return "\n\n".join(parts)
```

LightRAG then performs its own entity extraction (via the configured LLM) and KG construction. This runs **offline** — LightRAG's graph is built once and queried many times.

### Deployment
LightRAG runs as a sidecar service (`lightrag-server`). The adapter calls its REST API:
```
POST /query  {"query": "...", "mode": "hybrid"}
→ {"response": "...", "context": [...]}
```

---

## Component 3: Parallel Runner

**Purpose:** Run all activated fetchers and LightRAG concurrently using `asyncio.gather`, collecting results without blocking.

```python
async def run_parallel(query: str, active_fetchers: list[str]) -> dict[str, list[RetrievedChunk]]:
    tasks = {name: fetcher.afetch(query) for name, fetcher in registry.items() if name in active_fetchers}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    return {name: r for name, r in zip(tasks.keys(), results) if not isinstance(r, Exception)}
```

Exceptions from individual fetchers are caught and logged — a failure in one fetcher does not abort the entire retrieval.

**Latency profile (typical):**
- FastRAG: ~10ms
- HybridFetcher: ~50ms (first query: ~30s for BM25 rebuild)
- GraphRAGFetcher: ~150ms
- LightRAG API: ~500ms–2s (depends on LLM extraction)

Total parallel latency ≈ max of active fetchers ≈ 500ms–2s.

---

## Component 4: MultiSourceAggregator

**Purpose:** Take result lists from multiple fetchers and produce a single, deduplicated, source-labelled ranking.

### Steps

1. **Deduplication**: Remove chunks with identical `content_hash`. When two fetchers return the same passage, keep the one with the higher score.

2. **Source grouping**: Group by `source_name` (Stack Overflow, Wikipedia, etc.) — used for presentation, not ranking.

3. **RRF fusion**: Apply RRF across the ranked lists from each fetcher. A chunk that ranks highly in multiple fetchers gets a boosted RRF score.

```python
def rrf_merge(results: dict[str, list[RetrievedChunk]], k=60) -> list[RetrievedChunk]:
    scores: dict[str, float] = defaultdict(float)
    for fetcher_name, chunks in results.items():
        for rank, chunk in enumerate(chunks, start=1):
            scores[chunk.chunk_id] += 1.0 / (k + rank)
    return sorted(all_chunks, key=lambda c: scores[c.chunk_id], reverse=True)
```

---

## Component 5: CrossEncoderReranker

**Purpose:** Re-score the top-50 aggregated candidates by running query + passage through a cross-encoder model, then take top-10.

### Why cross-encoders after bi-encoders

Bi-encoders (used in dense retrieval) encode query and passage **independently** — they cannot model token-level interactions between query and passage. This is fast but loses fine-grained relevance signals.

Cross-encoders encode query + passage **jointly** (concatenated as `[CLS] query [SEP] passage [SEP]`). The full transformer attention mechanism can model interactions like:
- "The question asks about `async def` specifically, and this passage contains `async def` in a semantically matching context"
- "The entity in the query (`Python 3.11`) matches the exact version in this passage"

The cross-encoder is only run on the top-50 (not all 10M+ chunks) — this keeps it tractable.

### Model choice

| Model | Size | Latency (50 passages) | Notes |
|---|---|---|---|
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | 22M params | ~50ms | Fast, good quality |
| `BAAI/bge-reranker-v2-m3` | 568M params | ~300ms | Best quality, multilingual, recommended |
| `cross-encoder/ms-marco-electra-base` | 110M params | ~150ms | Good balance |

**Recommendation:** `BAAI/bge-reranker-v2-m3` for production (LightRAG uses this by default). `ms-marco-MiniLM-L-6-v2` for latency-sensitive deployments.

---

## Component 6: SynthesisEngine

**Purpose:** Given the top-10 re-ranked passages, generate a coherent, cited multi-source answer using an LLM.

### Prompt template

```
You are a precise Q&A assistant. Answer the question using ONLY the sources provided.
Cite each claim with [1], [2], etc. corresponding to the source number.
If sources disagree, note the disagreement explicitly.
If the answer cannot be determined from the sources, say "I cannot find a reliable answer in the available sources."

Question: {question}

Sources:
[1] {source_1_name} (relevance: {score_1:.2f}):
{excerpt_1}

[2] {source_2_name} (relevance: {score_2:.2f}):
{excerpt_2}

...

Answer:
```

### Key prompt constraints
- "ONLY the sources provided" — reduces hallucination
- "If sources disagree, note the disagreement" — forces faithfulness
- "If the answer cannot be determined..." — handles unanswerable cases gracefully
- Relevance scores are shown — the LLM can weight sources accordingly

### LLM client factory

```python
def get_llm_client(provider: str) -> LLMClient:
    if provider == "openai":       return OpenAIClient(model="gpt-4o")
    elif provider == "ollama":     return OllamaClient(model="qwen3:32b")
    elif provider == "litellm":    return LiteLLMClient()  # any OpenAI-compatible endpoint
    elif provider == "anthropic":  return AnthropicClient(model="claude-3-5-sonnet")
```

LiteLLM provides a unified interface across all providers — recommended for flexibility.

### Streaming support
The `/ask/stream` endpoint uses server-sent events (SSE) to stream the LLM synthesis token by token. This gives users immediate feedback while the full answer is being generated — critical for perceived latency.

---

## Component 7: CitationParser

**Purpose:** Extract `[1]`, `[2]`, `[3]` references from the LLM's output and resolve them back to `SourceCard` objects.

```python
def parse_citations(answer: str, sources: list[SourceCard]) -> dict[int, SourceCard]:
    pattern = r'\[(\d+)\]'
    cited_indices = {int(m) - 1 for m in re.findall(pattern, answer)}
    return {i+1: sources[i] for i in cited_indices if i < len(sources)}
```

The final response links every `[1]` in the answer text to a clickable `SourceCard` with URL, source name, excerpt, and score.

---

## Component 8: Guardrails

**Purpose:** Multi-layer validation to prevent contradictory, low-confidence, and indirect LLM responses. Inserted between retrieval and synthesis (Layer 1), into the prompt (Layer 2), and after generation (Layer 3).

### Layer 1 — Retrieval filtering (`guardrails/retrieval_filter.py`)

Applied to reranked chunks before they reach the LLM:

| Filter | What it does | Default |
|---|---|---|
| `filter_low_relevance` | Drops chunks below an absolute score threshold | `MIN_RERANK_SCORE=0.15` |
| `filter_score_gap` | Drops chunks scoring below 50% of the top chunk (relative) | `max_gap_ratio=0.5` |
| `cap_source_diversity` | Limits chunks from one source name | `MAX_SAME_SOURCE=2` |

The score-gap filter is critical because it works regardless of score scale — whether chunks have raw RRF scores or cross-encoder sigmoid scores.

### Layer 2 — Prompt hardening (`synthesis/prompt_builder.py`)

The system prompt enforces:
- **Direct-answer-first**: "Answer the question DIRECTLY in your FIRST sentence."
- **Ignore irrelevant sources**: "Do NOT mention or discuss sources that are irrelevant — pretend they do not exist."
- **Brevity for factual**: "One to two sentences for simple factual questions."
- **No negative leads**: "Do NOT start your answer with what something is NOT."

A `confidence_hint` is injected when the average reranker score falls below `LOW_CONFIDENCE_THRESHOLD` (default 0.3), warning the LLM that sources may have limited relevance.

### Layer 3 — Post-generation validation (`guardrails/response_validator.py`)

Lightweight heuristic checks (no extra LLM call) run on the completed answer:

| Check | Detection method |
|---|---|
| Negative lead | Regex: answer starts with "X is not", "No,", "That is incorrect" |
| Self-contradiction | Regex: "A is X... but/however A is not X" patterns |
| Low alignment | Keyword overlap between question and first sentence |
| Confidence gate | Low reranker score + flagged issues → disclaimer or fallback |

Results are surfaced as `guardrail_flags` on `BrainResponse` (e.g. `["negative_lead", "low_alignment"]`).

### Layer 3b — Optional LLM-as-judge (`guardrails/llm_judge.py`)

An opt-in second LLM call (`ENABLE_LLM_JUDGE=true`, off by default) that asks:
> "Does this answer directly and correctly address the question without contradiction? YES or NO."

Fail-open on errors. Intended for high-stakes deployments where latency/cost is acceptable.

### Design decision: Why heuristics over a second LLM call?

Heuristic checks add <1ms of latency and zero API cost. The LLM-as-judge adds 1-3s and doubles LLM cost. For most deployments, the prompt hardening + retrieval filtering eliminate the vast majority of bad responses. The LLM judge is available as a safety net for production environments that require it.

---

## Component 9: BrainResponse Schema

```python
@dataclass
class SourceCard:
    source_name: str        # "Stack Overflow", "Wikipedia", "HotpotQA" …
    excerpt: str            # The retrieved passage (truncated for display)
    url: str                # Original attribution URL
    score: float            # Cross-encoder re-rank score
    retrieval_method: str   # "dense", "graph", "bm25", "lightrag_hybrid"
    chunk_id: str           # Internal reference

@dataclass
class BrainResponse:
    question: str
    answer: str             # LLM-synthesised, with [1][2][3] inline citations
    sources: list[SourceCard]   # Ordered by re-rank score
    cited_sources: list[SourceCard]  # Only sources actually cited in the answer
    confidence: float       # Mean cross-encoder score of cited sources
    answer_type: str        # "factual", "multi_hop", "conceptual", "unanswerable"
    retrieval_trace: dict   # {fetchers_used, latencies, rrf_k, reranker_model}
    latency_ms: int
    guardrail_flags: list[str]  # e.g. ["negative_lead", "low_alignment"] — empty if all checks pass
```

---

## Component 10: Query Rewriter

Generates 2–3 query variants using a fast LLM call (128 max tokens) before retrieval. The original query is always variant #1 so retrieval quality never degrades. All variants are fetched in parallel via `asyncio.gather` over the existing `ParallelFetcher`, and results merge into the same RRF aggregation pipeline.

**Config**: `QUERY_REWRITE_ENABLED`, `QUERY_REWRITE_MAX_VARIANTS`

---

## Component 11: Context Compressor

Extractive sentence-level compression after reranking. Splits each chunk into sentences, computes cosine similarity against the query with sentence-transformers, and keeps only the top-N sentences (default 5) above a similarity threshold (default 0.25). Purely extractive — no LLM call.

**Config**: `CONTEXT_COMPRESSION_ENABLED`, `CONTEXT_COMPRESSION_MIN_SCORE`, `CONTEXT_COMPRESSION_TOP_SENTS`

---

## Component 12: Tiered LLM Routing

`TieredLLMClient` wraps two LLM clients and routes based on the router's complexity score:
- complexity < 0.35 → fast model (gemma4:e4b)
- complexity >= 0.35 → large model (mistral)

Degrades gracefully to single-model when `LLM_MODEL_FAST` isn't configured.

**Config**: `LLM_MODEL_FAST=gemma4:e4b`, `LLM_TIERED_THRESHOLD=0.35`

---

## Component 13: Three-Layer Cache

Queries pass through three cache layers in order:

| Layer | Mechanism | Latency | Hit condition |
|---|---|---|---|
| Exact-match | SHA256 of normalised text → `QueryCache` | ~4ms | Identical query |
| Semantic | Cosine similarity of query embeddings → `SemanticCache` | ~8ms | Similarity >= 0.92 |
| Embedding | LRU cache of query→vector → `EmbeddingCache` | <1ms | Same query text to embedder |

The semantic cache catches paraphrased queries (e.g. "What is X?" vs "How does X work?") that exact-match misses.

**Config**: `SEMANTIC_CACHE_ENABLED`, `SEMANTIC_CACHE_THRESHOLD=0.92`, `SEMANTIC_CACHE_MAXSIZE=1024`

---

## Full Pipeline: End-to-End Latency Budget

| Stage | Typical latency |
|---|---|
| QueryRouter | <5ms |
| Cache lookup (exact + semantic) | 5–10ms |
| Query rewriting (LLM, 2–3 variants) | 2–6s |
| Parallel retrieval (all fetchers × variants) | 500ms–2s |
| MultiSourceAggregator (RRF + dedup) | <10ms |
| CrossEncoderReranker (top-50) | 50–300ms |
| Guardrails Layer 1 (retrieval filtering) | <1ms |
| Context compression (sentence extraction) | <10ms |
| LLM synthesis (tiered: gemma4:e4b or mistral) | 3–13s |
| Guardrails Layer 3 (response validation) | <1ms |
| CitationParser + ResponseFormatter | <5ms |
| **Total** | **~10–18 seconds** (cold, no cache) |

Streaming synthesis reduces *perceived* latency — the user sees the first tokens within ~1s while the full answer completes. Semantic cache hits return in ~8ms.

---

## Paper Notes: What to Highlight

- The bi-encoder → cross-encoder two-stage retrieval pipeline is the standard production pattern (used by Google, Meta, etc.) — citing DPR (Karpukhin et al., 2020) and ColBERT (Khattab & Zaharia, 2020) is appropriate
- The prompt design (citation enforcement + disagreement instruction) is a key contribution — measure its effect on faithfulness vs a plain synthesis prompt
- The `retrieval_trace` field in `BrainResponse` is important for system interpretability — every answer includes a full audit trail of which fetchers were used and their latencies
- The streaming endpoint is an engineering contribution that significantly affects user experience but is rarely discussed in RAG papers
- LLM model recommendations from LightRAG paper (32B+ parameters, 32KB+ context): should be referenced and followed — smaller models produce lower-quality KG extraction
- The multi-layer guardrails system is a practical contribution: most RAG papers focus on retrieval quality but not on post-generation validation. The score-gap filter, negative-lead detection, and answer-question alignment checks are lightweight (<1ms) but catch common failure modes like the "Barcelona is not the capital" anti-pattern. Worth benchmarking: faithfulness scores with/without guardrails on the evaluation set

## Additional Citations
- Karpukhin et al. (2020) — *Dense Passage Retrieval for Open-Domain Question Answering* (DPR) — arXiv:2004.04906
- Khattab & Zaharia (2020) — *ColBERT: Efficient and Effective Passage Search* — arXiv:2004.12832
- Nogueira & Cho (2019) — *Passage Re-ranking with BERT* — arXiv:1901.04085
