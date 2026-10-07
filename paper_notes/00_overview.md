# 00 — Project Overview & Research Problem Statement

> Status: Living document. Updated as the system evolves.
> Last updated: April 9, 2026

---

## Project Title (Working)

**MultiRAG-QA: A Multi-Source Retrieval-Augmented Question Answering System with Knowledge Graph Reasoning and Attributed Synthesis**

Alternative titles:
- *Towards Comprehensive Q&A: Fusing Heterogeneous Open Knowledge Sources via Graph-Augmented Retrieval*
- *Multi-Source CQA: Bridging Community Q&A, Wikipedia, and Structured Datasets through Attributed RAG*

---

## Research Problem

Existing Q&A and Retrieval-Augmented Generation (RAG) systems suffer from three core limitations:

1. **Single-source brittleness** — Systems trained or indexed on one corpus (e.g. Wikipedia) cannot answer questions that require knowledge distributed across community Q&A forums, academic datasets, and encyclopaedic text simultaneously.

2. **Opaque attribution** — Most RAG systems return an answer without telling the user *which* source each claim originated from. This undermines trust, reproducibility, and auditability — especially in high-stakes domains.

3. **Retrieval strategy mismatch** — No single retrieval strategy dominates across all query types. Dense ANN retrieval excels at semantic similarity; BM25 at keyword matching; graph traversal at multi-hop relational reasoning. Real-world queries span all three types.

### Research Questions

- RQ1: Does fusing retrieval signals from heterogeneous open sources (Stack Exchange, Wikipedia, NQ, MS MARCO, HotpotQA, etc.) improve answer quality versus single-source RAG?
- RQ2: Does Knowledge Graph-augmented retrieval (via LightRAG) improve multi-hop question answering compared to dense-only retrieval?
- RQ3: Can a cross-encoder re-ranking step reliably select the most relevant passages before LLM synthesis, reducing hallucination?
- RQ4: What citation format and source-presentation design maximises user trust and verifiability in multi-source Q&A?

---

## System Summary

The system is a two-module pipeline:

### Module 1: Data Module (`data_module/`)

A fully modular ETL package that:
- Ingests QA data from **9 open/free sources** (Stack Exchange, Wikipedia, SQuAD 2.0, Natural Questions, MS MARCO, HotpotQA, TriviaQA, OpenAssistant OASST2, Wikidata)
- Normalises everything into a unified `CanonicalQA` Pydantic schema
- Stores data across **5 purpose-optimised backends**
- Exposes **4 retrieval strategies** as clean Python APIs

### Module 2: Brain Module (`brain_module/`) — *to be built*

The reasoning and synthesis layer that:
- Routes incoming queries to the appropriate retrieval strategy
- Runs retrieval in parallel across multiple fetchers + LightRAG
- Fuses results via Reciprocal Rank Fusion
- Re-ranks top candidates with a cross-encoder
- Synthesises a cited, multi-source answer via LLM
- Returns a structured `BrainResponse` with per-source attribution

### Overall Data Flow

```
User Query
    │
    ▼
QueryRouter (intent + complexity classification)
    │
    ├── FastRAG (dense ANN, LanceDB)
    ├── HybridFetcher (BM25 + dense, RRF)
    ├── GraphRAGFetcher (Neo4j expansion)
    └── LightRAG (KG-augmented hybrid)
    │
    ▼
MultiSourceAggregator (RRF fusion + dedup)
    │
    ▼
CrossEncoderReranker (top-50 → top-10)
    │
    ▼
SynthesisEngine (LLM + multi-source citation prompt)
    │
    ▼
BrainResponse { answer, sources[], confidence, trace }
```

---

## Scope & Boundaries

### In scope
- Open-licensed data sources only (CC BY-SA, Apache 2.0, CC0)
- English-centric retrieval/evaluation pipeline, with multilingual user input support at the UI layer
- Text-only retrieval and synthesis (multimodal is future work via RAG-Anything)
- Question answering, not document summarisation or generation

### Out of scope (for v1)
- Wikidata entity graph (data ingested but not yet linked to the Q&A pipeline)
- Real-time web search augmentation
- Fine-tuning any component model
- Reinforcement Learning from Human Feedback (RLHF)

---

## Novelty Claims (Preliminary)

1. **Unified schema across 9 heterogeneous open QA corpora** — CanonicalQA provides a single normalised representation across sources with incompatible formats (XML, JSON, Parquet, HF datasets).

2. **Multi-strategy retrieval fusion** — Systematic comparison of dense, sparse (BM25), graph-augmented, and hybrid retrieval strategies on the same data, fused via RRF.

3. **KG-augmented multi-source RAG** — Using LightRAG's local/global/hybrid modes over a knowledge graph derived from 9 sources, not a single corpus.

4. **Structured multi-source response with attribution** — Every answer includes ranked SourceCards linking each claim to its origin, enabling reproducibility and trust.

---

## Key Numbers (as of April 2026)

| Metric | Value |
|---|---|
| Data sources | 9 (Wikidata ingested but not yet linked) |
| Storage backends | 5 (Parquet, DuckDB, LanceDB, SQLite, Neo4j/NetworkX) |
| Retrieval strategies | 4 (FastRAG, GraphRAG, Hybrid, Agentic) |
| Chunking strategies | 5 (canonical_qa, per_answer, question_only, multi_hop, hierarchical) |
| Embedding models supported | 3+ (MiniLM-L6, MPNet-base, text-embedding-3-small) |

---

## References to Cite

- Lewis et al. (2020) — *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks* (original RAG paper) — arXiv:2005.11401
- Guo et al. (2024) — *LightRAG: Simple and Fast Retrieval-Augmented Generation* — arXiv:2410.05779
- Guo et al. (2025) — *RAG-Anything: All-in-One RAG Framework* — arXiv:2510.12323
- Cormack et al. (2009) — *Reciprocal Rank Fusion outperforms Condorcet and individual rank learning methods*
- Es et al. (2023) — *RAGAS: Automated Evaluation of Retrieval Augmented Generation* — arXiv:2309.15217
- Rajpurkar et al. (2018) — *SQuAD 2.0* — arXiv:1806.03822
- Kwiatkowski et al. (2019) — *Natural Questions: A Benchmark for Question Answering Research*
- Bajaj et al. (2018) — *MS MARCO: A Human Generated MAchine Reading COmprehension Dataset*
- Yang et al. (2018) — *HotpotQA: A Dataset for Diverse, Explainable Multi-hop Question Answering*
- Joshi et al. (2017) — *TriviaQA: A Large Scale Distantly Supervised Challenge Dataset for Reading Comprehension*
- Köpf et al. (2023) — *OpenAssistant Conversations (OASST2)*
