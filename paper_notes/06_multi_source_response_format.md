# 06 — Multi-Source Response Format

> This document covers the design of the structured multi-source response: BrainResponse schema, SourceCard design, citation format, and UX rationale.

---

## The Core UX Problem

Most RAG systems present answers in one of two unsatisfying ways:

1. **Answer only** — "The GIL prevents true multi-threading." No source. No way to verify. Trust-reducing for technical users.
2. **Raw document list** — Here are 10 passages. Figure it out yourself. Cognitively demanding; no synthesis.

The goal is a third option: **a synthesised answer with inline citations and expandable source cards** — the format used by academic papers, but adapted for conversational interfaces.

The user gets:

- A readable, direct answer (not 10 raw passages)
- Inline `[1][2]` citations they can click to expand
- Per-source confidence scores so they know which sources to trust
- Attribution URLs for CC BY-SA compliance and reproducibility
- A retrieval trace for power users / debugging

---

## BrainResponse — Full Schema

```python
@dataclass
class SourceCard:
    # Identity
    chunk_id: str                 # Internal chunk reference
    source_name: str              # Human-readable: "Stack Overflow", "Wikipedia"
    source_enum: str              # Machine-readable: "stackexchange", "wikipedia"
    url: str                      # Attribution URL (CC BY-SA requirement)
    
    # Content
    excerpt: str                  # Passage text (truncated for display, ~200 chars)
    full_text: str                # Full passage for expansion (not sent by default)
    
    # Quality signals
    score: float                  # Cross-encoder re-rank score (0–1)
    retrieval_method: str         # "dense_ann" | "bm25_hybrid" | "graph_expansion" | "lightrag_local" | "lightrag_global"
    
    # Metadata
    tags: list[str]               # Source tags (e.g. ["python", "async"])
    answer_score: int | None      # Stack Exchange vote score, if applicable
    is_accepted: bool | None      # Stack Exchange accepted answer flag, if applicable
    language: str                 # "en", "de", etc.
    created_at: str | None        # Original post date, if available

@dataclass
class RetrievalTrace:
    fetchers_used: list[str]      # Which fetchers were activated
    fetcher_latencies_ms: dict[str, int]
    rrf_k: int                    # RRF k parameter used
    reranker_model: str           # Cross-encoder model name
    total_candidates_before_rerank: int
    total_candidates_after_rerank: int
    lightrag_mode: str | None     # "local" | "global" | "hybrid" | None

@dataclass
class BrainResponse:
    # Core
    question: str
    answer: str                   # LLM-synthesised with [1][2] inline citations
    answer_type: str              # "factual" | "multi_hop" | "conceptual" | "unanswerable"
    
    # Sources
    sources: list[SourceCard]     # All sources retrieved (ordered by score)
    cited_sources: list[SourceCard]   # Only sources actually cited in the answer
    
    # Quality
    confidence: float             # Mean re-rank score of cited sources
    is_answered: bool             # False if LLM returned "I cannot find..."
    
    # Meta
    retrieval_trace: RetrievalTrace
    latency_ms: int
    llm_model: str                # Which LLM generated the answer
    timestamp: str                # ISO 8601
```

---

## Citation Format Design

### Inline citation style: `[1]`, `[2]`, `[3]`

This is the most familiar citation style for technical users (academic papers, Wikipedia). It is compact and does not interrupt reading flow.

**Alternative considered: footnote-style**
`The GIL prevents true multi-threading¹` with numbered footnotes at the bottom. Rejected — footnote superscripts are harder to render consistently across platforms (web, mobile, CLI) and require more UI work.

**Alternative considered: (Author, Year)**
Academic citation style. Rejected — sources like Stack Overflow don't have authors or years in a useful sense. Source name + relevance score is more informative.

### Synthesis prompt enforcement

The citation format is enforced in the synthesis prompt:

```
Cite each claim with [1], [2], etc. corresponding to the source number above.
If a claim is supported by multiple sources, list all: [1][3].
Do NOT include a claim that has no source citation.
```

The `CitationParser` then validates that every `[N]` in the output maps to a valid source:

```python
# Detect hallucinated citations (indices beyond the source list)
invalid_citations = {i for i in extracted_indices if i >= len(sources)}
if invalid_citations:
    log_warning(f"LLM cited non-existent sources: {invalid_citations}")
```

---

## SourceCard Design Rationale

### Why include `retrieval_method`

Different retrieval methods have different failure modes:

- `dense_ann`: may miss keyword-specific passages
- `bm25_hybrid`: may over-index on rare tokens
- `lightrag_global`: community summaries may be stale if the corpus is small

Showing `retrieval_method` in the UI (or at least in the trace) helps diagnose why a specific source was retrieved. In evaluation, it allows per-method quality analysis.

### Why include `answer_score` and `is_accepted` for Stack Overflow

Stack Overflow's community voting is a strong quality signal. An accepted answer with 500 upvotes is far more trustworthy than a single answer with 0 votes. This signal is:

1. Shown in the SourceCard UI (badge: "Accepted Answer ✓", vote count)
2. Used as a tie-breaker in aggregation (all else equal, prefer higher-voted answers)
3. Logged for evaluation (do high-voted answers correlate with higher Ragas faithfulness scores?)

### Why `excerpt` vs `full_text`

The `excerpt` (~200 chars) is what the frontend renders by default — enough to understand the source without overwhelming the UI. The `full_text` is available on expand (click to show more). This is the standard pattern used by Google's AI Overviews and Perplexity AI.

The LLM synthesis step uses the full text (up to the context window limit). The display truncates for readability.

---

## JSON Wire Format

The REST API returns:

```json
{
  "question": "What is Python's GIL and how does it affect async code?",
  "answer": "Python's Global Interpreter Lock (GIL) prevents multiple native threads from executing Python bytecodes simultaneously [1]. However, async I/O (asyncio) sidesteps the GIL because it uses a single-threaded event loop [2][3]. For CPU-bound tasks, you still need multiprocessing [1].",
  "answer_type": "conceptual",
  "is_answered": true,
  "confidence": 0.87,
  "sources": [
    {
      "chunk_id": "se_12345_0",
      "source_name": "Stack Overflow",
      "source_enum": "stackexchange",
      "url": "https://stackoverflow.com/questions/12345",
      "excerpt": "The GIL prevents multiple native threads from executing Python bytecodes simultaneously...",
      "score": 0.94,
      "retrieval_method": "bm25_hybrid",
      "tags": ["python", "multithreading", "gil"],
      "answer_score": 342,
      "is_accepted": true,
      "language": "en"
    },
    {
      "chunk_id": "wiki_gil_0",
      "source_name": "Wikipedia",
      "source_enum": "wikipedia",
      "url": "https://en.wikipedia.org/wiki/Global_interpreter_lock",
      "excerpt": "A global interpreter lock (GIL) is a mechanism used in computer language interpreters...",
      "score": 0.87,
      "retrieval_method": "dense_ann",
      "tags": [],
      "answer_score": null,
      "is_accepted": null,
      "language": "en"
    }
  ],
  "cited_sources": [/* same as sources, filtered to only [1][2][3] */],
  "retrieval_trace": {
    "fetchers_used": ["fast_rag", "hybrid", "lightrag_hybrid"],
    "fetcher_latencies_ms": {"fast_rag": 12, "hybrid": 48, "lightrag_hybrid": 820},
    "rrf_k": 60,
    "reranker_model": "BAAI/bge-reranker-v2-m3",
    "total_candidates_before_rerank": 47,
    "total_candidates_after_rerank": 10,
    "lightrag_mode": "hybrid"
  },
  "latency_ms": 1423,
  "llm_model": "gpt-4o",
  "timestamp": "2026-04-06T12:34:56Z"
}
```

---

## Streaming Response Format (SSE)

For the `/ask/stream` endpoint, the response is streamed as Server-Sent Events:

```
event: sources
data: {"sources": [...]}       ← sources returned immediately (before LLM)

event: answer_token
data: {"token": "Python's"}

event: answer_token
data: {"token": " Global"}

... (per token)

event: done
data: {"confidence": 0.87, "latency_ms": 1423, "retrieval_trace": {...}}
```

This pattern (sources first, then streaming answer) is the same pattern used by Perplexity AI. Users see the source cards appear instantly, then watch the answer build word by word — dramatically improving perceived responsiveness.

---

## Multi-Source Display Hierarchy

When rendering in a UI, the recommended hierarchy:

```
┌─────────────────────────────────────────────────────┐
│  Q: What is Python's GIL?                           │
│                                                     │
│  A: Python's GIL prevents multiple native           │
│     threads [1]. Async I/O sidesteps this [2][3].   │
│                                                     │
│  Confidence: ████████░░ 87%                         │
├─────────────────────────────────────────────────────┤
│  Sources (3 cited of 10 retrieved)                  │
│                                                     │
│  [1] Stack Overflow  ✓ Accepted  ▲342               │
│      "The GIL prevents multiple native threads..."  │
│      python › multithreading › gil  [Expand ↓]      │
│                                                     │
│  [2] Wikipedia                                      │
│      "A global interpreter lock (GIL) is a..."      │
│      [Expand ↓]                                     │
│                                                     │
│  [3] Natural Questions                              │
│      "asyncio uses a single-threaded event loop..." │
│      [Expand ↓]                                     │
├─────────────────────────────────────────────────────┤
│  Retrieved from: Stack Overflow · Wikipedia ·       │
│  MS MARCO · Natural Questions · SQuAD               │
│  Latency: 1.4s  │  [Debug trace ↓]                  │
└─────────────────────────────────────────────────────┘
```

---

## Paper Notes: What to Highlight

- The `cited_sources` vs `sources` distinction is important — not all retrieved passages need to be shown. Showing only cited sources reduces information overload while the full source list is available for inspection.
- The streaming pattern (sources first, then token-by-token answer) is a UX design choice that significantly affects perceived latency — worth measuring in a user study.
- The `confidence` score (mean cross-encoder score of cited sources) is a novel quality signal for RAG systems — most systems return answers without any self-reported confidence. Measuring calibration of this score is future work.
- The `retrieval_trace` field enables full reproducibility: given any response, you can reconstruct exactly which fetchers ran, which candidates were considered, and which LLM was used.
- CC BY-SA compliance: the `url` field in every SourceCard is mandatory — not optional — because CC BY-SA 4.0 requires per-record attribution of original source URL. This is a legal requirement, not a design choice.

