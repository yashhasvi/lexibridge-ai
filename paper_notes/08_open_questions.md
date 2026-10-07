# 08 — Open Questions & Future Work

> This document records unresolved design decisions, known limitations, and directions for future work. Keeping this honest strengthens the paper's limitations section.

---

## Unresolved Design Decisions

### 1. LightRAG Sidecar vs Integrated

**Decision pending:** Should LightRAG run as a separate sidecar service (Option A) or be integrated directly as a Python library within the brain module (Option B)?

**Option A (sidecar):**
- Pros: Clean separation of concerns, LightRAG can be upgraded independently, REST API is language-agnostic
- Cons: Network latency (~2–5ms), requires managing two processes, more complex deployment

**Option B (embedded library):**
- Pros: No network hop, simpler deployment, direct function calls
- Cons: LightRAG's internal state is mixed with brain module state, harder to upgrade independently

**Lean:** Option A for production. Option B for local dev/research. Use environment flag to toggle.

---

### 2. BM25 Index Persistence

**Current state:** `HybridFetcher` rebuilds the BM25 index from Parquet on every startup. This takes 5–30 seconds depending on corpus size and blocks the first query.

**Options:**
- Pickle the BM25 index to disk and load on startup
- Use Elasticsearch or OpenSearch (which persist BM25 indexes natively) — LightRAG now integrates OpenSearch as of 2026.03

**Impact:** Blocking first query is unacceptable in production. This must be resolved before production deployment.

---

### 3. Re-ranker Model Choice

**Unresolved:** `BAAI/bge-reranker-v2-m3` (568M, better quality, multilingual) vs `cross-encoder/ms-marco-MiniLM-L-6-v2` (22M, faster, English-only).

**How to resolve:** Run ablation study (see `07_evaluation_plan.md`, Ablation B) and measure the quality/latency trade-off. The answer will depend on whether the quality gain from the larger model justifies the ~6x latency increase.

---

### 4. Optimal k for Sources in Synthesis Prompt

**Unresolved:** How many source passages should be included in the LLM synthesis prompt? (see `07_evaluation_plan.md`, Ablation D)

**Trade-off:**
- More sources → more complete answer, but: higher LLM latency, higher cost, potential attention dilution
- Fewer sources → faster, cheaper, but: may miss relevant information

**Current default:** k=10 (top-10 after re-ranking). To be validated by ablation.

---

### 5. QueryRouter Threshold Tuning

**Unresolved:** The complexity score thresholds (when to activate GraphRAG, when to activate LightRAG) are currently heuristic-based. They should be optimised against the evaluation set.

**Method:** Grid search over threshold combinations, measure Ragas faithfulness + context precision. Or: use DSPy to learn optimal routing (v2 work item).

---

### 6. Wikidata Entity Linking

**Current state:** Wikidata triples are ingested into the graph store, but the `EntityMention.wikidata_id` field is not populated. spaCy NER detects entities but doesn't link them to Wikidata Q-IDs.

**What's needed:**
- A label → Q-ID lookup table (built from Wikidata label dumps)
- Pass this table to `Enricher(run_entity_linking=True, wikidata_index=label_to_qid)`
- The `EntityMention` objects will then have `wikidata_id` populated
- Cross-source entity matching becomes possible: a "Python" entity in Stack Overflow links to the same Q-ID as "Python" in Wikipedia

**Impact:** Without Wikidata linking, the graph's `MENTIONS` edges connect questions to entity strings (e.g. "Python") rather than canonical entity IDs. Two sources that mention "Python 3" and "Python (programming language)" are not recognised as the same entity.

**This is the single most impactful incomplete feature in the current system.**

---

### 7. Streaming Synthesis and Source Pre-loading

**Design question:** Should retrieved sources be returned to the client *before* the LLM synthesis starts? (Answer: Yes — see `06_multi_source_response_format.md`, SSE format.)

**Unresolved:** How to handle the case where the LLM cites source [4] but the client only displayed sources [1][2][3] because it received them before synthesis completed?

**Solution options:**
- Always send all retrieved sources upfront, let the LLM cite from them
- Send sources progressively as the LLM cites them (harder to implement)
- Send all sources immediately, mark cited ones after synthesis (recommended)

---

## Known Limitations

### L1: LLM-dependent KG quality

LightRAG's KG is built by an LLM during ingestion. The quality of entity extraction depends directly on the LLM used. Using a smaller/cheaper model for ingestion produces noisier KGs with more missed entities and incorrect relationships. This is a fundamental trade-off between ingestion cost and retrieval quality.

**Mitigation:** Use Qwen3-32B (or equivalent) for KG extraction. Accept that full re-indexing is needed when switching LLMs.

---

### L2: Static KG (no real-time updates)

The knowledge graph is built offline from ingested data. New Stack Overflow posts, Wikipedia edits, and newly created answers are not reflected until a re-ingestion run. This means the system has a temporal staleness problem for rapidly evolving topics.

**Mitigation:** Nightly incremental ingestion pipeline. SQLite's `content_hash` dedup makes incremental runs efficient.

---

### L3: English-only

All 9 ingested sources are English. The retrieval pipeline uses English-trained embedding models. Non-English queries will produce poor results.

**Mitigation:** Switch to `BAAI/bge-m3` (multilingual embedding model) as the vector index. Add multilingual sources (Wikipedia in other languages, multilingual QA datasets). OpenAssistant OASST2 does contain non-English conversations — this is a low-hanging fruit.

---

### L4: BM25 index memory footprint

The BM25 index for large corpora (10M+ chunks from Stack Overflow + Wikipedia) requires significant RAM. At ~100 bytes per term-document pair, a 10M document corpus with average 50 unique terms = ~5GB RAM.

**Mitigation:** Elasticsearch or OpenSearch for BM25 at scale (both are now supported by LightRAG).

---

### L5: No user feedback loop

The current system has no mechanism to learn from user interactions (clicks, ratings, corrections). Every query is independent — the system does not improve with use.

**This was flagged as the #1 improvement priority in `IMPROVEMENT_ANALYSIS.md`.**

**Mitigation:** Add feedback endpoints → store to database → use feedback for re-ranking weight tuning → eventually DSPy optimisation.

---

### L6: Unanswerable question detection is LLM-prompt-dependent

The system's ability to say "I cannot find a reliable answer" depends on the synthesis prompt instruction. If the LLM ignores the instruction (common with smaller models), it will confabulate an answer from irrelevant sources.

**Mitigation:** Add a separate confidence threshold check: if the mean cross-encoder score of all retrieved passages is below a threshold (e.g. 0.4), bypass LLM synthesis and return "Low confidence — no reliable answer found."

---

## Future Work

### F1: Wikidata Entity Linking (High Priority)

Complete the `EntityMention` → Wikidata Q-ID pipeline. This enables:
- Cross-source entity matching ("Python" in SE = "Python" in Wikipedia = Q28865 in Wikidata)
- Richer graph edges (entities have types, properties, relationships from Wikidata)
- Entity-centric UI (click on "Python" in an answer to see all related passages across sources)

---

### F2: RAG-Anything Integration (Medium Priority)

When the system needs to ingest raw documents (PDFs, research papers, technical manuals), switch to RAG-Anything's ingestion pipeline. The brain module is unchanged — only the data module's ingestion path changes.

---

### F3: DSPy Optimisation (Medium Priority)

After the Ragas evaluation pipeline is running, use DSPy to automatically optimise:
- The synthesis prompt (few-shot examples selected to maximise faithfulness)
- The retrieval k parameter
- The QueryRouter thresholds

This could be a paper contribution in itself: "Automatic Optimisation of Multi-Source RAG Pipelines via DSPy."

---

### F4: User Feedback Loop (High Priority)

Add feedback collection:
- Per-source "was this helpful?" button
- Answer rating (1–5 stars)
- Correction submission ("the actual answer is...")

Use collected feedback to:
- Re-weight sources in RRF (sources users find helpful → higher weight)
- Build a fine-tuning dataset for the synthesis LLM
- Train the QueryRouter on real query distributions

---

### F5: Multilingual Expansion

- Switch embedding to `BAAI/bge-m3`
- Add multilingual QA datasets (XQuAD, TyDiQA, MKQA)
- Enable multilingual query → multilingual retrieval → English synthesis (or multilingual synthesis)

---

### F6: Citation Verification

After synthesis, use a separate verification LLM call to check each citation is correctly attributed:
```
"The answer states [1] supports claim X. Does the excerpt from [1] support claim X? Yes/No."
```

This is a "self-critique" pass that catches cases where the LLM incorrectly cites a source.

---

### F7: Temporal Awareness

Add `created_at` filtering to retrieval: for questions about recent events or fast-changing topics, prefer more recent sources. Stack Exchange posts from 2024 about Python 3.12 are more relevant than posts from 2015 about Python 2.7.

---

### F8: Domain-Specific Routing

Add domain classifiers: programming, science, history, legal, medical. Route to domain-specific sub-indexes with domain-tuned embedding models and rerankers. The `tags` field in `CanonicalQA` enables this naturally for Stack Exchange data.

---

## What Wikidata Would Have Added

Wikidata is ingested but not yet linked. Its full potential in this system:

1. **Entity disambiguation:** "Python" (programming language, Q28865) vs "Python" (snake, Q2083) — without Wikidata linking, the graph cannot distinguish these.

2. **Cross-source entity resolution:** Stack Overflow's "Guido van Rossum" and Wikipedia's "Guido van Rossum" would link to the same Wikidata entity (Q480458), allowing cross-source passages about the same person to be retrieved together.

3. **Structured knowledge injection:** Wikidata properties (P31/P279: instance-of/subclass-of) enable structured queries like "what are all subclasses of programming language?" — retrievable directly from the graph.

4. **Entity type filtering:** "Find all questions about Python libraries (Q21127166 and its subclasses)" — a structured filter that cannot be expressed as a vector query.

The gap: Wikidata entity linking requires a label → Q-ID lookup step that adds ~10ms per NER entity. This is tractable. The implementation gap is in the `Enricher.run_entity_linking` path.

---

## Paper Limitations Section Outline

1. LLM-dependent KG quality (L1) — acknowledge the trade-off, measure KG completeness
2. Static KG staleness (L2) — describe the incremental ingestion mechanism
3. English-only (L3) — note it as a scope limitation, describe multilingual path
4. No user feedback (L5) — note as future work (F4)
5. Evaluation dataset quality (semi-automatic, LLM-generated) — note limitations vs human annotation
6. Wikidata entity linking incomplete — note specific impact on cross-source entity resolution
