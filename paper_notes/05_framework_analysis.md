# 05 — Framework Analysis

> This document covers the analysis of external frameworks considered for the brain module: LightRAG, RAG-Anything, LlamaIndex, DSPy, Haystack, and others. Records why each was chosen or not chosen.

---

## The Core Decision: Which Framework Powers the Brain?

The brain module needs: KG-augmented retrieval, multi-source fusion, LLM synthesis, and evaluation. Multiple frameworks offer overlapping capabilities. This document records the analysis.

---

## LightRAG

**Paper:** Guo et al. (2024), *LightRAG: Simple and Fast Retrieval-Augmented Generation*, arXiv:2410.05779
**GitHub:** https://github.com/HKUDS/LightRAG
**Stars (Apr 2026):** ~32K
**License:** MIT

### What it does

LightRAG is a graph-augmented RAG framework that builds a Knowledge Graph from ingested documents and uses it for retrieval. It extends naive RAG with two retrieval modes:

- **Local mode:** Extracts entities from the query → retrieves their KG neighbourhood → provides entity-centric context to the LLM
- **Global mode:** Builds community-level summaries of the KG (via Leiden algorithm) → answers broad thematic questions using high-level summaries
- **Hybrid mode:** Both local and global simultaneously — best for general queries
- **Naive mode:** Standard vector similarity only — no KG

### Why we chose LightRAG

| Criterion | Assessment |
|---|---|
| KG-augmented retrieval | Native — core feature, not a plugin |
| Neo4j integration | Yes — first-class, used in production |
| Vector store integration | Yes — LanceDB, Milvus, Chroma, Qdrant, PostgreSQL |
| Embedding model flexibility | Yes — any OpenAI-compatible, Ollama, HuggingFace |
| LLM flexibility | Yes — same as above |
| REST API server | Yes — `lightrag-server` with WebUI |
| RAGAS integration | Yes — built in as of 2025.11 |
| Open source | MIT license |
| Active development | Yes — 68 releases, 6,894 commits |
| Multi-hop reasoning | Yes — via graph traversal in local/hybrid mode |

LightRAG is the **only** open-source framework that combines KG construction, KG-augmented retrieval, vector retrieval, and evaluation (RAGAS) in a single deployable package that also supports Neo4j natively.

### Performance (from the paper)

LightRAG outperforms NaiveRAG, RQ-RAG, HyDE, and GraphRAG on all four test domains (Agriculture, Computer Science, Legal, Mixed) across Comprehensiveness, Diversity, and Empowerment metrics. Against GraphRAG (Microsoft), LightRAG wins on all domains except Mixed/Comprehensiveness (near tie).

Key result: LightRAG outperforms GraphRAG while being significantly faster and cheaper (GraphRAG requires expensive community report generation).

### Limitations

- Requires an LLM for KG extraction during ingestion — this is a one-time cost but it is slow and expensive for large corpora. LightRAG recommends 32B+ parameter models.
- LightRAG builds its own internal KG and vector store — it does not natively plug into the existing `data_module` graph store. The solution is to run LightRAG as a sidecar with its own state, populated by an ingestion adapter.
- The global mode relies on pre-computed community summaries — these must be recomputed when the corpus changes significantly.

---

## RAG-Anything

**Paper:** Guo et al. (2025), *RAG-Anything: All-in-One RAG Framework*, arXiv:2510.12323
**GitHub:** https://github.com/HKUDS/RAG-Anything
**Stars (Apr 2026):** ~15K
**License:** MIT

### What it does

RAG-Anything is built on top of LightRAG and adds:
- **Document parsing:** PDF, DOCX, PPTX, XLSX via MinerU, Docling, or PaddleOCR
- **Multimodal content processing:** Images (VLM captioning), tables (structured analysis), equations (LaTeX parsing)
- **Direct content list insertion:** Bypass parsing by inserting pre-parsed content lists
- **VLM-enhanced queries:** When retrieved context contains images, automatically includes them in the LLM prompt

### Why we did NOT choose RAG-Anything (for now)

Our data is **already ingested and structured** in `CanonicalQA` format. We do not have raw PDFs, Office documents, or images to parse. RAG-Anything's primary value-add is its document parsing pipeline — which we do not need.

Using RAG-Anything would add:
- `mineru` as a dependency (heavy, requires separate installation)
- VLM infrastructure for image processing (unnecessary overhead)
- Complexity without benefit for text-only ingestion

**Decision:** Use LightRAG directly. RAG-Anything is a clear upgrade path if/when the system needs to ingest PDFs (e.g. research papers, technical documentation).

### When to switch to RAG-Anything

If the project later needs to:
- Ingest arXiv papers or Stack Overflow documentation PDFs
- Process tables in research papers
- Handle equations in technical content

Since RAG-Anything is built on LightRAG with the same API, the switch is a drop-in upgrade.

---

## LlamaIndex

**GitHub:** https://github.com/run-llama/llama_index
**License:** MIT

### Relevant capabilities

- `RouterQueryEngine`: Routes queries to different retrieval indexes based on query type
- `SubQuestionQueryEngine`: Decomposes complex questions into sub-questions, retrieves each, synthesises
- `CitationQueryEngine`: Built-in citation extraction from retrieved passages
- Native connectors for LanceDB, Neo4j, and most vector/graph stores
- LightRAG integration available via community packages

### Role in our architecture

LlamaIndex was considered as the **orchestration layer** on top of LightRAG and the existing fetchers. The `RouterQueryEngine` would replace our custom `QueryRouter`, and `CitationQueryEngine` would replace our `CitationParser`.

**Decision:** Build custom orchestration for now. LlamaIndex adds significant dependency weight and its abstractions sometimes hide important details (e.g. exact prompts used, how RRF is computed). For a research system where we need full control over every component for ablation studies, custom implementations are preferable.

**Revisit:** If the project needs to scale beyond the current team, LlamaIndex's batteries-included approach becomes more attractive.

---

## DSPy (Stanford)

**Paper:** Khattab et al. (2023), *DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines*, arXiv:2310.03714
**GitHub:** https://github.com/stanfordnlp/dspy
**License:** MIT

### What it does

DSPy is a framework for **programmatic LLM pipelines** that can be automatically optimised. Instead of writing prompts manually, you define a program in terms of input/output signatures, and DSPy optimises the prompts and retrieval parameters using a small set of labelled examples.

Example:
```python
class MultiSourceQA(dspy.Module):
    def __init__(self):
        self.retrieve = dspy.Retrieve(k=10)
        self.generate = dspy.ChainOfThought("context, question -> answer")
    
    def forward(self, question):
        context = self.retrieve(question)
        return self.generate(context=context, question=question)

# Compile with teleprompter (automatic prompt optimisation)
compiled = BootstrapFewShot(metric=answer_exact_match).compile(MultiSourceQA(), trainset=...)
```

### Why DSPy is relevant but not yet adopted

DSPy is most powerful when you have a **labelled evaluation set** to optimise against. Without it, DSPy's compilation step is not meaningfully different from manual prompt engineering.

**Decision:** Adopt DSPy in v2 after building the evaluation pipeline (Ragas). Once we can measure answer quality, DSPy can automatically optimise the synthesis prompt and retrieval parameters against that metric.

This is a significant research opportunity — using DSPy to automatically optimise a multi-source RAG pipeline could be a paper contribution in itself.

---

## Haystack (deepset)

**GitHub:** https://github.com/deepset-ai/haystack
**License:** Apache 2.0

### Assessment

Haystack is a mature production RAG framework with a pipeline abstraction. It has connectors for most vector databases and supports hybrid retrieval.

**Why not chosen:** Haystack's pipeline abstraction is optimised for document Q&A (single corpus), not multi-source retrieval from heterogeneous datasets with different schema. Adapting it to our CanonicalQA schema would require more work than building custom components. LightRAG is more aligned with our KG-centric approach.

---

## Ragas

**Paper:** Es et al. (2023), *RAGAS: Automated Evaluation of Retrieval Augmented Generation*, arXiv:2309.15217
**GitHub:** https://github.com/explodinggradients/ragas
**License:** Apache 2.0

### What it does

Ragas provides **reference-free evaluation** of RAG systems. Given a question, a generated answer, and the retrieved context passages, it computes:

| Metric | What it measures | How computed |
|---|---|---|
| **Faithfulness** | Does the answer contain only claims supported by the context? | LLM extracts claims from answer → checks each against context |
| **Answer Relevancy** | Does the answer actually address the question? | LLM generates questions from answer → cosine sim to original question |
| **Context Precision** | Are the retrieved passages actually relevant to the question? | LLM judges each passage's relevance |
| **Context Recall** | Did retrieval capture all information needed to answer? | LLM checks if answer ground truth can be attributed to context |

**Why Ragas is ideal for this project:**
- Reference-free (no gold answers needed for most metrics) — critical since we don't have human-written gold answers for all 9 sources
- LLM-based metrics generalise better than token-overlap metrics (BLEU, ROUGE) for open-ended answers
- Now integrated directly into LightRAG's codebase

### Integration in our system

Ragas is called automatically in the `brain_module/evaluation/ragas_eval.py` wrapper after each response:
```python
result = ragas_evaluate(
    question=response.question,
    answer=response.answer,
    contexts=[s.excerpt for s in response.sources],
)
# result.faithfulness, result.answer_relevancy, result.context_precision, result.context_recall
```

This allows A/B testing of different configurations (different reranker, different synthesis prompt) against Ragas metrics without human annotation.

---

## vLLM / Ollama — Local LLM Serving

**vLLM:** High-throughput LLM serving engine, PagedAttention, continuous batching. Suitable for multi-user production deployment.
**Ollama:** Simple local LLM serving, one-command model download. Suitable for development and single-user deployment.

### LLM recommendations (from LightRAG paper)

LightRAG recommends:
- **Minimum:** 32B parameters
- **Context length:** 32KB minimum, 64KB recommended
- **Not recommended:** Reasoning models (o1, o3) during indexing — they are slow and add unnecessary verbosity to KG extraction
- **Recommended for indexing:** Qwen3-30B-A3B (mixture-of-experts, fast)
- **Recommended for query synthesis:** Stronger models than indexing (GPT-4o, Claude 3.5 Sonnet)

---

## Summary Decision Table

| Framework | Role | Decision | Reason |
|---|---|---|---|
| **LightRAG** | KG-augmented retrieval core | **Adopted** | Only framework with native KG+vector+Neo4j+RAGAS |
| **RAG-Anything** | Multimodal document parsing | **Future work** | Data already ingested; not needed for text-only |
| **LlamaIndex** | Orchestration | **Deferred** | Custom orchestration preferred for research control |
| **DSPy** | Prompt/pipeline optimisation | **v2 candidate** | Needs evaluation set first |
| **Haystack** | Pipeline framework | **Not chosen** | Less aligned with multi-source KG approach |
| **Ragas** | Evaluation | **Adopted** | Reference-free, LLM-based, now in LightRAG |
| **Ollama** | Local LLM serving | **Adopted (dev)** | Simple, free, supports Qwen3-32B |
| **vLLM** | Production LLM serving | **Production path** | High throughput when needed |
| **LiteLLM** | LLM client abstraction | **Adopted** | Unified API across all providers |
