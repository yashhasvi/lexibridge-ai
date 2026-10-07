# 🚀 MultiRAG-QA

**Multi-Source Retrieval-Augmented Question Answering with Knowledge Graph Reasoning**

---

## 📌 Overview

**MultiRAG-QA** is an end-to-end **Community Question Answering (CQA) retrieval and generation system** designed to overcome the **lexical gap, multi-hop reasoning challenges, and lack of attribution** in traditional QA systems.

Unlike conventional RAG systems that rely on a single retrieval method, this project combines:

* 🔍 Multiple retrieval strategies
* 🧠 Knowledge Graph reasoning
* ⚡ Parallel retrieval + fusion
* 📚 Multi-source attribution with citations

The result is a **highly accurate, explainable, and scalable QA system**. 

---

## 🎯 Key Features

### 🔄 Multi-Strategy Retrieval

* Dense semantic search (ANN)
* Keyword-based search (BM25)
* Graph-based retrieval (Neo4j)
* Knowledge Graph retrieval (LightRAG)

👉 These strategies run in **parallel** and are fused using **Reciprocal Rank Fusion (RRF)** for better accuracy. 

---

### 🧠 Knowledge Graph Augmentation

* Uses entity relationships (tags, duplicates, mentions)
* Enables **multi-hop reasoning**
* Connects information across different sources

---

### ⚡ Intelligent Query Routing

* Classifies queries into:

  * Factual
  * Conceptual
  * Technical
  * Multi-hop
* Activates only required retrieval strategies → **reduces latency**

---

### 📊 Cross-Encoder Re-ranking

* Improves precision by re-ranking top candidates
* Uses models like:

  * `bge-reranker`
  * `MiniLM`

---

### 📝 Multi-Source Answer Generation

* Synthesizes answers using LLM
* Provides:

  * ✅ Inline citations `[1][2]`
  * ✅ Source attribution
  * ✅ Confidence score

---

### 🛡️ Guardrails & Reliability

* Retrieval filtering
* Prompt constraints
* Post-generation validation
* Prevents hallucinations and contradictions 

---

### ⚡ Performance Optimizations

* Query rewriting (improves recall)
* Context compression (reduces token usage)
* Embedding cache + semantic cache
* Tiered LLM routing (fast + large models) 

---

## 🏗️ System Architecture

```
User Query
    ↓
Query Router (intent + complexity)
    ↓
Parallel Retrieval:
    • FastRAG (Dense)
    • Hybrid (BM25 + Dense)
    • GraphRAG
    • LightRAG
    ↓
RRF Aggregation + Deduplication
    ↓
Cross-Encoder Re-ranking
    ↓
Context Compression
    ↓
LLM Synthesis (with citations)
    ↓
BrainResponse Output
```

👉 The system is built as **two main modules**:

* `data_module/` → ingestion, storage, retrieval
* `brain_module/` → reasoning, ranking, synthesis 

---

## 🗂️ Project Structure

```
MultiRAG-QA/
│
├── data_module/
│   ├── ingest/            # Data ingestion pipelines
│   ├── fetch/             # Retrieval strategies
│   ├── storage/           # Parquet, LanceDB, SQLite, Neo4j
│
├── brain_module/
│   ├── router/            # Query classification
│   ├── retrieval/         # Parallel fetch execution
│   ├── aggregation/       # RRF fusion
│   ├── reranking/         # Cross-encoder models
│  ├── synthesis/         # LLM answer generation
│   ├── guardrails/        # Validation layers
│   ├── cache/             # Query & embedding cache
│   ├── api/               # FastAPI endpoints
│
├── config/
├── evaluation/
├── README.md
```

---

## 📚 Data Sources

The system integrates **9 open datasets** into a unified schema:

* Stack Exchange
* Wikipedia
* SQuAD 2.0
* Natural Questions
* MS MARCO
* HotpotQA
* TriviaQA
* OpenAssistant
* Wikidata

All are normalized into a **CanonicalQA schema** for unified retrieval. 

---

## 🗄️ Storage Architecture

Uses **5 specialized backends**:

| Backend | Purpose          |
| ------- | ---------------- |
| Parquet | Cold storage     |
| DuckDB  | Analytics        |
| LanceDB | Vector search    |
| SQLite  | Metadata + dedup |
| Neo4j   | Knowledge graph  |

👉 Each backend handles a **specific workload efficiently**. 

---

## 📊 Evaluation

The system is evaluated using **RAGAS metrics**:

* Faithfulness
* Answer Relevancy
* Context Precision
* Context Recall

Also benchmarked on:

* SQuAD
* HotpotQA
* Natural Questions

👉 Focus: **multi-source + multi-hop performance improvement** 

---

## ⚙️ Setup Instructions

### 1️⃣ Clone the repository

```bash
git clone https://github.com/your-repo/multirag-qa.git
cd multirag-qa
```

### 2️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

### 3️⃣ Start backend

```bash
cd brain_module
uvicorn api.main:app --reload
```

### 4️⃣ Open frontend

```
http://localhost:5173
```

---

## 🚀 API Usage

### Ask a question

```bash
POST /ask
```

### Streaming response

```bash
POST /ask/stream
```

Returns:

* Answer with citations
* Sources
* Confidence
* Retrieval trace

---

## 📈 Performance Snapshot

* ⏱ Avg latency: ~14.7s (CPU environment)
* 📊 Avg confidence: ~0.82
* 📚 Avg sources: 2.4
* ⚡ Cache hit rate: 20%

👉 Performance improves significantly with GPU + caching. 

---

## 🔬 Research Contributions

* Multi-strategy retrieval fusion
* KG-augmented multi-source RAG
* Structured citation-based responses
* Query-aware retrieval routing
* Guardrail-based reliability system

---

## ⚠️ Limitations

* No real-time updates (static dataset)
* English-only (currently)
* BM25 index rebuild on startup
* Wikidata entity linking incomplete

👉 These are active areas for improvement. 

---

## 🔮 Future Work

* Multilingual support
* User feedback loop
* DSPy-based optimization
* Wikidata entity linking
* RAG-Anything (multimodal support)

---

## 📄 License

This project uses **open datasets (CC BY-SA, Apache 2.0, CC0)**.
Ensure attribution when redistributing derived data.

---

## 🤝 Contributors

This is a **group project** developed as part of research in:

* Multi-source QA
* Retrieval-Augmented Generation
* Knowledge Graph reasoning

---

## ⭐ Final Note

This system is designed not just to **answer questions**, but to:

✔ Explain *why* the answer is correct
✔ Show *where* it came from
✔ Handle *complex real-world queries*

---
