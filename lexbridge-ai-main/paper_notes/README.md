# Paper Notes — Master Index

> Working notes for the MultiRAG-QA research paper.
> Total: 10 files, ~102KB of content.
> Last updated: April 9, 2026

---

## Files

| File | Contents | Key paper section |
|---|---|---|
| [00_overview.md](00_overview.md) | Project title, research questions, system summary, key numbers, references list | Abstract, Introduction |
| [01_data_sources.md](01_data_sources.md) | All 9 sources: licenses, access methods, schema mapping, skipped sources | Dataset section |
| [02_storage_architecture.md](02_storage_architecture.md) | Five-backend design: Parquet, DuckDB, LanceDB, SQLite, Neo4j | System Architecture |
| [03_retrieval_strategies.md](03_retrieval_strategies.md) | Four fetchers, chunking strategies, RRF, embedding models | Methodology: Retrieval |
| [04_brain_architecture.md](04_brain_architecture.md) | Brain module: QueryRouter, LightRAG, aggregator, cross-encoder, synthesis, response schema | Methodology: Brain |
| [05_framework_analysis.md](05_framework_analysis.md) | LightRAG vs RAG-Anything, LlamaIndex, DSPy, Ragas — why each was chosen or not | Related Work |
| [06_multi_source_response_format.md](06_multi_source_response_format.md) | BrainResponse schema, citation format, SourceCard, streaming, UX | System Design |
| [07_evaluation_plan.md](07_evaluation_plan.md) | Ragas metrics, ablation studies, benchmarks, baseline comparisons, tables to report | Evaluation |
| [08_open_questions.md](08_open_questions.md) | Unresolved decisions, known limitations, future work, Wikidata gap | Limitations, Future Work |
| [09_project_updates_log.md](09_project_updates_log.md) | Dated implementation changelog (latest practical updates; frontend notes kept concise) | Appendix / Project Log |

---

## Key Claims to Validate Experimentally

1. Multi-strategy retrieval (all fetchers + RRF) outperforms any single strategy
2. LightRAG hybrid mode improves multi-hop QA (HotpotQA F1) over dense-only
3. Cross-encoder re-ranking improves context precision and faithfulness
4. Citation enforcement in synthesis prompt reduces hallucination (higher faithfulness)
5. The confidence score (mean re-rank score of cited sources) is calibrated (correlates with actual correctness)

---

## Key References (Quick List)

- Lewis et al. (2020) RAG — arXiv:2005.11401
- Guo et al. (2024) LightRAG — arXiv:2410.05779
- Guo et al. (2025) RAG-Anything — arXiv:2510.12323
- Es et al. (2023) Ragas — arXiv:2309.15217
- Cormack et al. (2009) RRF — SIGIR 2009
- Karpukhin et al. (2020) DPR — arXiv:2004.04906
- Khattab & Zaharia (2020) ColBERT — arXiv:2004.12832
- Khattab et al. (2023) DSPy — arXiv:2310.03714
- Rajpurkar et al. (2018) SQuAD 2.0 — arXiv:1806.03822
- Yang et al. (2018) HotpotQA — arXiv:1809.09600
- Kwiatkowski et al. (2019) Natural Questions
- Bajaj et al. (2018) MS MARCO
- Joshi et al. (2017) TriviaQA
- Köpf et al. (2023) OpenAssistant OASST2
