# 07 — Evaluation Plan

> This document covers how to measure system quality: Ragas metrics, ablation studies, benchmark datasets, baseline comparisons, and what numbers to report in the paper.

---

## Why Evaluation Is Non-Trivial for Multi-Source RAG

Standard NLP evaluation metrics (BLEU, ROUGE, exact match) are inadequate for open-ended RAG:

- **BLEU/ROUGE** measure n-gram overlap — an answer can be factually correct but lexically different from the reference and score near zero
- **Exact match** only works for extractive QA (span extraction) — not for synthesised multi-source answers
- **Human evaluation** is the gold standard but expensive, slow, and hard to reproduce

We use three complementary evaluation approaches:
1. **Ragas** — automatic, reference-free, LLM-based (primary)
2. **Dataset benchmarks** — use existing dataset labels as ground truth (secondary)
3. **Ablation studies** — measure the contribution of each component (tertiary)

---

## Ragas Metrics

**Reference:** Es et al. (2023), arXiv:2309.15217
**Integration:** Built into LightRAG; wrapped in `brain_module/evaluation/ragas_eval.py`

### The four primary metrics

#### 1. Faithfulness

**What:** Does the answer contain only claims that can be attributed to the retrieved context?

**How computed:**
1. LLM extracts all factual claims from the generated answer
2. For each claim, LLM judges whether it is directly supported by at least one retrieved passage
3. `Faithfulness = (# supported claims) / (# total claims)`

**Range:** 0.0–1.0. Higher = less hallucination.

**Target:** > 0.90 (answers should be almost entirely grounded in sources)

**Why it matters:** This directly measures the system's tendency to hallucinate. A faithfulness of 0.75 means 25% of the answer's claims are not supported by any retrieved source.

---

#### 2. Answer Relevancy

**What:** Does the generated answer actually address the question that was asked?

**How computed:**
1. LLM generates N synthetic questions from the generated answer
2. Embed each synthetic question and the original question
3. `Answer Relevancy = mean cosine similarity(synthetic questions, original question)`

**Range:** 0.0–1.0. Higher = more on-topic.

**Target:** > 0.85

**Why it matters:** An answer can be faithful (all claims grounded) but still off-topic (it answers a different question than was asked). This catches topic drift.

---

#### 3. Context Precision

**What:** Are the retrieved passages actually relevant to answering the question?

**How computed:**
1. For each retrieved passage (in ranked order), LLM judges whether it is useful for answering the question
2. `Context Precision = Σ(precision@k × relevance@k) / (# relevant passages)`

**Range:** 0.0–1.0. Higher = better retrieval quality.

**Target:** > 0.75

**Why it matters:** This measures retrieval quality independently of generation. Low context precision means the retriever is returning irrelevant passages that pollute the LLM's context.

---

#### 4. Context Recall

**What:** Did the retrieval step capture all the information needed to answer the question?

**How computed (requires reference answer):**
1. Reference answer is broken into factual claims
2. For each claim, LLM judges whether it is attributable to any retrieved passage
3. `Context Recall = (# claims attributable to context) / (# total claims in reference)`

**Range:** 0.0–1.0. Higher = more complete retrieval.

**Note:** Context Recall requires a reference answer — we use dataset labels (SQuAD, NQ, HotpotQA) for this metric.

**Target:** > 0.80

---

### Running Ragas

```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall

result = evaluate(
    dataset={
        "question": [response.question],
        "answer": [response.answer],
        "contexts": [[s.excerpt for s in response.sources]],
        "ground_truth": [reference_answer],  # Optional: for context_recall
    },
    metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
)
```

---

## Dataset Benchmarks

For datasets where we have ground-truth answers, we can compute traditional metrics alongside Ragas.

### SQuAD 2.0 — Extractive QA benchmark

**Ground truth:** Exact answer span from Wikipedia passage

**Metrics:**
- **Exact Match (EM):** Is the answer string exactly equal to the ground truth? (strict)
- **F1 token overlap:** Token-level F1 between answer and ground truth (lenient)
- **Has-answer detection:** For unanswerable questions, does the system return "I cannot find..."?

**Baseline:** SQuAD 2.0 fine-tuned BERT achieves EM=66.3, F1=69.1. Our system (generative RAG) is not directly comparable but should match or exceed on has-answer detection.

---

### Natural Questions — Open-Domain QA benchmark

**Ground truth:** Short answer span (1–5 tokens typically)

**Metrics:** EM, F1
**Key challenge:** NQ answers are often entity names ("Paris", "Marie Curie") — the LLM synthesis may rephrase these, lowering EM while being semantically correct. Use fuzzy matching.

---

### HotpotQA — Multi-Hop QA benchmark

**Ground truth:** Answer + supporting facts (list of Wikipedia sentence IDs)

**Metrics:**
- Answer EM + F1
- **Supporting Fact F1:** Did the retrieved passages include the correct supporting facts?

This is the key benchmark for our GraphRAG + LightRAG hypothesis: multi-hop questions should show larger improvement over dense-only retrieval here than on SQuAD.

---

### TriviaQA — Trivia QA benchmark

**Ground truth:** Answer string (with aliases)

**Metrics:** EM (with alias matching), F1

---

## Ablation Studies

The ablation study measures the contribution of each component by removing it and measuring the delta.

### A: Retrieval strategy ablation

Compare each retrieval strategy in isolation vs combination:

| Configuration | Description |
|---|---|
| Dense only (baseline) | FastRAG only, no re-ranking |
| BM25 only | HybridFetcher with BM25 weight = 1.0 |
| Hybrid | HybridFetcher (BM25 + dense) |
| Graph only | GraphRAGFetcher only |
| LightRAG local | LightRAG in local mode |
| LightRAG global | LightRAG in global mode |
| LightRAG hybrid | LightRAG in hybrid mode |
| **Full system** | All fetchers + RRF + re-ranking |

**Hypothesis:** The full system (all fetchers + RRF) outperforms any single strategy. LightRAG hybrid outperforms dense-only on HotpotQA specifically.

---

### B: Re-ranking ablation

| Configuration | Description |
|---|---|
| No re-ranking | Top-10 from RRF, directly to synthesis |
| BM25 re-ranking | Re-rank by BM25 score |
| Cross-encoder small | `ms-marco-MiniLM-L-6-v2` (22M) |
| Cross-encoder large | `BAAI/bge-reranker-v2-m3` (568M) |

**Hypothesis:** Cross-encoder re-ranking significantly improves context precision and faithfulness vs no re-ranking.

---

### C: Synthesis prompt ablation

| Configuration | Description |
|---|---|
| No prompt constraints | Just "Answer this question using the sources" |
| Citation enforcement | Add "[1][2]" citation requirement |
| Disagreement instruction | Add "note if sources disagree" |
| Unanswerable instruction | Add "if cannot determine, say so" |
| **Full prompt** | All constraints combined |

**Hypothesis:** Each prompt constraint independently improves a different Ragas metric:
- Citation enforcement → higher faithfulness (anchors claims to sources)
- Disagreement instruction → better handling of conflicting sources
- Unanswerable instruction → better has-answer detection on SQuAD 2.0 unanswerable

---

### D: Source count ablation

How many sources should be shown to the LLM?

| Configuration | k (sources in synthesis) |
|---|---|
| k=1 | Only the top-ranked source |
| k=3 | Top 3 |
| k=5 | Top 5 |
| k=10 | Top 10 |
| k=20 | Top 20 |

**Hypothesis:** There is a sweet spot around k=5–10. Beyond k=10, additional context degrades answer quality (LLM attention dilution) while increasing latency and cost.

---

## Baselines to Compare Against

| Baseline | Description |
|---|---|
| Naive RAG | Single-source dense retrieval, no re-ranking, no KG |
| BM25-only | Keyword search, no neural components |
| Wikipedia-only | Single-source (Wikipedia) dense RAG — common in literature |
| LightRAG (standalone) | LightRAG without our custom fetchers |
| GPT-4o without retrieval | Zero-shot LLM answer with no retrieved context |

---

## Evaluation Dataset Construction

For questions not covered by existing benchmarks (Stack Overflow answers, OpenAssistant conversations), we need to construct an evaluation set.

### Method: LLM-generated evaluation questions

1. Sample 1,000 `CanonicalQA` records across all sources
2. Use GPT-4o to generate a natural language question from each record's title + best answer
3. Store as `(question, ground_truth_answer, source_name)` triples
4. Use these as the Ragas evaluation set

This is a semi-automatic approach — not as reliable as human annotation but tractable at scale.

### Size targets

| Source | Evaluation questions |
|---|---|
| Stack Overflow | 200 |
| Wikipedia | 150 |
| SQuAD 2.0 | 200 (use existing dev set) |
| Natural Questions | 200 (use existing dev set) |
| HotpotQA | 200 (use existing dev set) |
| MS MARCO | 100 |
| TriviaQA | 100 (use existing test set) |
| OpenAssistant | 100 |
| **Total** | **~1,250** |

---

## What Numbers to Report in the Paper

### Table 1: System Configuration Comparison (Ablation A)

| System | HotpotQA F1 | NQ EM | SQuAD F1 | Faithfulness | Context Precision |
|---|---|---|---|---|---|
| Dense only | — | — | — | — | — |
| BM25 + Dense | — | — | — | — | — |
| + Graph expansion | — | — | — | — | — |
| + LightRAG hybrid | — | — | — | — | — |
| + Cross-encoder | — | — | — | — | — |
| **Full system** | — | — | — | — | — |

### Table 2: Ragas Metrics by Source

| Source | Faithfulness | Answer Relevancy | Context Precision | Context Recall |
|---|---|---|---|---|
| Stack Overflow | — | — | — | — |
| Wikipedia | — | — | — | — |
| HotpotQA | — | — | — | — |
| … | — | — | — | — |

### Table 3: Latency by Configuration

| Stage | P50 (ms) | P95 (ms) | P99 (ms) |
|---|---|---|---|
| QueryRouter | — | — | — |
| Parallel retrieval | — | — | — |
| Aggregation + RRF | — | — | — |
| Cross-encoder (top-50) | — | — | — |
| LLM synthesis | — | — | — |
| **Total** | — | — | — |

---

## Paper Notes: What to Highlight

- The multi-source Ragas evaluation (Table 2) is novel — prior Ragas papers evaluate on a single corpus; we evaluate across 8 heterogeneous sources and can measure which sources produce the highest-quality context
- The ablation studies (especially retrieval strategy ablation) are the core empirical contribution — they directly test the hypothesis that multi-strategy retrieval outperforms single-strategy
- HotpotQA is the critical benchmark for the KG hypothesis: we predict the graph-augmented strategies show the largest improvement here
- Latency reporting (Table 3) is important for a production system paper — many RAG papers ignore latency entirely
- The evaluation dataset construction method (LLM-generated questions from CanonicalQA records) should be described carefully — it is not gold human annotation but is reproducible and scalable
