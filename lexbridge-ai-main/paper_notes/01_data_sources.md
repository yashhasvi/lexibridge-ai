# 01 — Data Sources

> This document covers all 9 ingested sources: design decisions, licensing, access methods, schema mapping, and what was skipped and why.

---

## Design Philosophy

The core challenge in building a multi-source Q&A system is that every open QA corpus was designed independently, with different:
- Schema structures (XML, JSON, Parquet, HF Arrow)
- Answer formats (free text, HTML, ranked lists, conversation trees)
- Metadata conventions (tags, scores, votes, timestamps)
- Licensing terms

Rather than building source-specific retrieval pipelines, we designed a **single canonical schema** (`CanonicalQA`) that all sources normalise into. This enables retrieval, deduplication, and evaluation to operate uniformly regardless of source.

---

## The CanonicalQA Schema

```python
class CanonicalQA(BaseModel):
    canonical_id: str          # SHA256 of (source + source_id)
    source: SourceName         # enum: STACKEXCHANGE, WIKIPEDIA, ...
    source_id: str             # original ID in the source system
    source_url: str            # attribution URL (CC BY-SA requirement)
    title: str                 # question title or article title
    body_markdown: str         # normalised body text (HTML stripped)
    tags: list[str]            # topic tags
    answers: list[CanonicalAnswer]
    entity_mentions: list[EntityMention]  # from spaCy NER
    content_hash: str          # SHA256 of title+body for dedup
    language: str              # ISO 639-1
    created_at: datetime | None
    license: License           # enum
```

Key design decisions:
- **`content_hash`** enables deterministic deduplication that survives restarts (stored in SQLite)
- **`source_url`** is mandatory — CC BY-SA requires per-record attribution
- **`answers` is a list** — Stack Exchange has multiple ranked answers; NQ has a single short answer; SQuAD has a span answer; all are normalised to the same `CanonicalAnswer` type
- **`entity_mentions`** are populated by spaCy NER during the transform pipeline, enabling graph edge construction

---

## Source-by-Source Notes

### 1. Stack Exchange (April 2024 Archive)

| Property | Value |
|---|---|
| License | CC BY-SA 4.0 |
| Access | `archive.org/details/stackexchange` (7z XML) |
| Scale | 60M+ posts across 170+ sites |
| Format | SAX-parsed XML (`Posts.xml`, `PostLinks.xml`) |

**Why April 2024 archive (not the official download):**
Since July 2024, Stack Overflow's profile-gated download requires agreeing to: *"I do not intend to use this file for training an LLM."* This post-dates CC BY-SA and would restrict lawful use. The April 2024 Internet Archive mirror predates this gate. The underlying CC BY-SA 4.0 license permits all uses including ML training.

**Implementation notes:**
- Two-pass SAX parser: first pass collects all answers (keyed by `ParentId`), second pass joins questions to their accepted/top answers
- Memory footprint kept flat via streaming — no full XML load into RAM
- `PostLinks.xml` provides `DUPLICATE_OF` and `RELATED_TO` edges for the knowledge graph
- Sites ingested: stackoverflow, unix, superuser, askubuntu, serverfault (configurable via `config/sources/stackexchange.yaml`)

**Schema mapping decisions:**
- `Title` → `title`
- `Body` (HTML) → `body_markdown` (stripped by BeautifulSoup, code fences preserved as backtick blocks)
- `Score` → `CanonicalAnswer.score`
- `AcceptedAnswerId` → `CanonicalAnswer.is_accepted = True`
- `Tags` → `tags` (pipe-delimited string split and normalised)

---

### 2. Wikipedia

| Property | Value |
|---|---|
| License | CC BY-SA 4.0 + GFDL |
| Access | HuggingFace `wikimedia/wikipedia` dataset |
| Scale | ~6.7M English articles |
| Format | HF Arrow (Parquet-cached on first download) |

**Role in the system:**
Wikipedia provides encyclopaedic background knowledge. While it is not a Q&A corpus itself, it serves as the primary evidence source for Natural Questions and TriviaQA, and provides entity context for the knowledge graph.

**Implementation notes:**
- Each article is mapped as a single `CanonicalQA` where `title` = article title, `body_markdown` = article text (first 4000 chars)
- No answers (empty `answers` list) — Wikipedia entries serve as context passages, not Q&A pairs
- Future work: sliding-window chunker for long articles (currently uses first 4000 chars only)

---

### 3. SQuAD 2.0

| Property | Value |
|---|---|
| License | CC BY-SA 4.0 |
| Access | HuggingFace `rajpurkar/squad_v2` |
| Scale | ~150K QA pairs (130K answerable + 53K unanswerable) |
| Format | HF Arrow |

**Why SQuAD 2.0 over SQuAD 1.1:**
SQuAD 2.0 includes ~53K unanswerable questions (adversarially constructed). This is important for training the system to recognise when no answer exists in context — a critical capability for a trustworthy Q&A system.

**Key property — context paragraph:**
Each SQuAD record includes the source Wikipedia paragraph used to extract the answer. This is stored as a separate chunk (`ChunkType.CONTEXT`) linked to the parent question via `parent_chunk_id`, enabling hierarchical retrieval.

---

### 4. Natural Questions (NQ)

| Property | Value |
|---|---|
| License | CC BY-SA 3.0 |
| Access | HuggingFace `google-research-datasets/natural_questions` |
| Scale | ~300K QA pairs |
| Format | HF Arrow |

**Why NQ is valuable:**
NQ queries come from real Google search logs — they represent actual information needs, not researcher-constructed questions. This makes NQ the closest proxy to real user queries in the dataset.

**Implementation notes:**
- Short answer spans are used as `CanonicalAnswer.body_markdown`
- Long answer (full Wikipedia passage) is stored as context
- Questions with no short answer are retained as unanswerable examples

---

### 5. MS MARCO

| Property | Value |
|---|---|
| License | CC BY 4.0 (more permissive than CC BY-SA) |
| Access | HuggingFace `microsoft/ms_marco` |
| Scale | 1M+ queries, 8.8M passages |
| Format | HF Arrow |

**Why MS MARCO is valuable:**
MS MARCO's answers are passage-level (not span-level), sourced from Bing search results. This represents a different answer style — more like what a search engine retrieves rather than what a human writes. Important for diversity.

**Note:** CC BY 4.0 (not CC BY-SA) — derivative works do not need to be CC BY-SA. This is the most permissive license in the collection.

---

### 6. HotpotQA

| Property | Value |
|---|---|
| License | CC BY-SA 4.0 |
| Access | HuggingFace `hotpot_qa` |
| Scale | ~113K QA pairs |
| Format | HF Arrow |

**Why HotpotQA is uniquely important:**
HotpotQA requires **multi-hop reasoning** — the answer requires synthesising information from two or more Wikipedia passages. This is exactly the use case that dense-only retrieval fails on and that Knowledge Graph retrieval excels at.

**Implementation notes:**
- `supporting_facts` field provides the reasoning chain — stored as separate `CONTEXT` chunks with `multi_hop` chunking strategy
- `type` field (`bridge` vs `comparison`) is stored in metadata for analysis
- Each supporting passage becomes a graph node linked to the question via `SUPPORTS` edge

---

### 7. TriviaQA

| Property | Value |
|---|---|
| License | Apache 2.0 (most permissive) |
| Access | HuggingFace `mandarjoshi/trivia_qa` |
| Scale | ~95K QA pairs |
| Format | HF Arrow |

**Why TriviaQA:**
TriviaQA provides fact-heavy trivia questions with Wikipedia and web evidence. Its Apache 2.0 license places no share-alike restrictions on derivatives. Questions are longer and more complex than SQuAD.

---

### 8. OpenAssistant OASST2

| Property | Value |
|---|---|
| License | Apache 2.0 |
| Access | HuggingFace `OpenAssistant/oasst2` |
| Scale | ~91K messages across 36K trees |
| Format | HF Arrow (message trees) |

**Why OASST2 is structurally different:**
OASST2 is a **conversation tree**, not a flat Q&A dataset. Each record is a `message` node in a tree with `parent_id`, `role` (prompter/assistant), `rank`, and quality metadata.

**Implementation notes:**
- Two-pass tree mapper: first pass builds message trees keyed by `message_tree_id`, second pass reconstructs Q+A pairs as (first prompter message, best assistant reply)
- Quality filtering: only `message_tree_state == "ready_for_export"` trees are used
- Toxicity filtering: messages with `labels.toxicity > 0.3` are excluded
- This dataset introduces **conversational** Q&A — distinct from factoid or reading comprehension

---

### 9. Wikidata

| Property | Value |
|---|---|
| License | CC0 (fully unrestricted — public domain) |
| Access | `dumps.wikimedia.org/wikidatawiki/entities` |
| Scale | ~100M+ entity/property triples |
| Format | Compressed JSON lines |

**Role in the system:**
Wikidata is not a Q&A corpus. It is a **structured knowledge base** of entities and relationships. Its role is to:
1. Provide entity disambiguation (map named entity strings → canonical Wikidata Q-IDs)
2. Populate the knowledge graph with `P31/P279` (instance-of/subclass-of) edges
3. Enable entity linking in the NER pipeline (`EntityMention.wikidata_id`)

**Current status: Ingested but not yet linked to the Q&A pipeline.**
The triple extractor writes Wikidata triples to the graph store, but the entity linking from `EntityMention` → Wikidata Q-ID is not yet wired end-to-end. This is the primary gap in the current system.

---

## What Was Skipped and Why

### Yahoo CQA (Community Q&A)
**Reason:** Yahoo WebScope dataset requires academic registration and a non-commercial agreement that prohibits LLM training use. This would conflict with the project's goal of being fully open and reproducible. Not included.

### Reddit / r/AskScience, r/explainlikeimfive
**Reason:** Reddit's terms of service restrict bulk data collection. PushShift (the primary Reddit archiver) was shut down in 2023. Not included.

### Quora Question Pairs
**Reason:** Quora's dataset is available on Kaggle but terms restrict commercial use. Not included.

### CommonCrawl-based QA (WebQuestions, WebGPT)
**Reason:** WebQuestions requires the Freebase API (deprecated). WebGPT (OpenAI) is not open-licensed. Not included.

---

## Data Licensing Summary

| Source | License | Share-Alike? | Commercial OK? |
|---|---|---|---|
| Stack Exchange | CC BY-SA 4.0 | Yes | Yes |
| Wikipedia | CC BY-SA 4.0 + GFDL | Yes | Yes |
| Wikidata | CC0 | No | Yes |
| SQuAD 2.0 | CC BY-SA 4.0 | Yes | Yes |
| Natural Questions | CC BY-SA 3.0 | Yes | Yes |
| MS MARCO | CC BY 4.0 | No | Yes |
| HotpotQA | CC BY-SA 4.0 | Yes | Yes |
| TriviaQA | Apache 2.0 | No | Yes |
| OpenAssistant OASST2 | Apache 2.0 | No | Yes |

**Key implication:** Any derivative dataset published from this system must be released under CC BY-SA (due to the CC BY-SA sources), or only the Apache/CC0/CC-BY-only subsets can be used in a more permissively licensed derivative.

---

## Paper Notes: What to Highlight

- The unified `CanonicalQA` schema is a contribution in itself — prior multi-source RAG systems typically treat each source as a separate retrieval index rather than normalising to a common schema
- The decision to use the April 2024 Archive.org Stack Exchange mirror (rather than the official post-July 2024 download) deserves explicit mention as it directly affects reproducibility
- The inclusion of unanswerable questions (SQuAD 2.0) is important for system robustness and should be measured in evaluation
- Wikidata's CC0 license makes it uniquely valuable as an unrestricted knowledge base — the entity linking gap is a clear future work item
