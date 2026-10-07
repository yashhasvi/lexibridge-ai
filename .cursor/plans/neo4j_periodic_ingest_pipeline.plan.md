---
name: Neo4j Periodic Graph Ingest Pipeline
overview: Design and implement a periodic data ingestion pipeline that keeps the Neo4j knowledge graph up-to-date with new data sources, re-extracts entities/triples, precomputes graph neighborhoods, and caches entity summaries for faster query-time retrieval.
todos:
  - id: incremental-ingest
    content: Add incremental ingest mode to GraphBuilder — only process new/updated records since last watermark
    status: pending
  - id: periodic-scheduler
    content: Create a scheduler (cron or APScheduler) that triggers graph ingest on a configurable interval
    status: pending
  - id: neighborhood-precompute
    content: Precompute k-hop neighborhoods for high-degree entities and cache in Neo4j node properties
    status: pending
  - id: entity-summary-cache
    content: Generate and cache LLM summaries for frequently-accessed entities at ingest time
    status: pending
  - id: stale-pruning
    content: Add stale entity/triple pruning — remove graph data from deleted or outdated source documents
    status: pending
  - id: health-monitoring
    content: Add graph health metrics (node/edge counts, last ingest timestamp, stale entity ratio) to /health endpoint
    status: pending
isProject: false
---

# Neo4j Periodic Graph Ingest Pipeline

## Problem

The current graph ingestion is a one-shot batch process:
1. `data-pipeline run` calls `GraphBuilder` which extracts entities/triples from canonical records
2. `export_to_neo4j.py` or `export_to_neo4j_admin.py` does a one-time migration from pickle to Neo4j
3. No mechanism exists to incrementally update the graph when new documents are ingested
4. No precomputation of graph neighborhoods — Cypher traversals happen at query time (~280ms per subgraph query)
5. No cached entity summaries — graph entities are re-processed on every query

## Current Architecture

```
data_module/
├── pipelines/
│   ├── orchestrator.py          # Stage 5e: GraphBuilder (batch, full reprocess)
│   └── graph/
│       └── builder.py           # TripleExtractor → store.upsert_entities/triples
├── storage/
│   └── graph_store.py           # Neo4jGraphStore (MERGE-based upsert) + NetworkXGraphStore
├── scripts/
│   ├── run_pipeline.py          # CLI: data-pipeline run (full batch)
│   └── export_to_neo4j.py       # One-time pickle → Neo4j migration
└── config/
    └── storage.yaml             # graph.backend: neo4j, credentials
```

### Key constraints
- `Neo4jGraphStore.upsert_entities()` uses `MERGE` — safe for re-ingestion (idempotent)
- `Neo4jGraphStore.upsert_triples()` uses `MERGE` on `triple_id` — also idempotent
- No `save()` method needed for Neo4j (writes are immediate)
- Brain module reads graph at query time via `get_subgraph()` (depth 1-3, limit 300 paths)

---

## Proposed Pipeline Design

### 1. Incremental Ingest Mode

Add a watermark-based incremental mode to `GraphBuilder`:
- Track last successful ingest timestamp in a Neo4j node property or SQLite table
- On each run, only process `CanonicalQA` records with `created_at > last_watermark`
- Use existing `MERGE` operations (already idempotent)
- Update watermark on success

### 2. Periodic Scheduler

Options (in order of preference):
- **APScheduler** — in-process, runs alongside the brain module or as a sidecar
- **Cron job** — `0 */6 * * * cd /path/to/prj && python -m data_module.scripts.run_pipeline --incremental`
- **Celery Beat** — if Redis is already available (it is)

Recommended: APScheduler with configurable interval (default: every 6 hours).

### 3. Graph Neighborhood Precomputation

After each ingest cycle, run a Neo4j APOC/Cypher job:
```cypher
// For entities with degree > threshold (e.g. 10)
MATCH (e:Entity)
WHERE size((e)--()) > 10
WITH e
MATCH path = (e)-[*1..2]-(neighbor:Entity)
WITH e, collect(DISTINCT neighbor.entity_id) AS hood
SET e.precomputed_neighbors_2hop = hood
```
- Store serialized neighbor lists as node properties
- `GraphRAGFetcher` checks `precomputed_neighbors_2hop` before running live Cypher
- Expected speedup: ~280ms → <5ms for cached entities

### 4. Entity Summary Cache

For high-degree entities, generate LLM summaries at ingest time:
```python
# During periodic job
for entity in high_degree_entities:
    triples = graph_store.get_subgraph(entity.id, depth=1)
    summary = await llm_client.complete([
        {"role": "system", "content": "Summarize this entity based on its relationships."},
        {"role": "user", "content": format_triples(triples)}
    ])
    # Store in Neo4j
    graph_store.set_property(entity.id, "cached_summary", summary)
```

### 5. Stale Data Pruning

When source documents are deleted or updated:
- Mark entities/triples from that source as `stale`
- After a grace period (configurable, default 7 days), prune stale entries
- Maintain a `source_document_id` on each triple for provenance tracking

### 6. Health Monitoring

Add to `/health` endpoint:
```json
{
  "graph": {
    "node_count": 45230,
    "edge_count": 128450,
    "last_ingest": "2026-04-10T14:00:00Z",
    "stale_ratio": 0.02,
    "precomputed_entities": 1250
  }
}
```

---

## Environment Variables

```
GRAPH_INGEST_INTERVAL_HOURS=6        # periodic interval
GRAPH_INGEST_ENABLED=true            # master switch
GRAPH_PRECOMPUTE_MIN_DEGREE=10       # min entity degree for precomputation
GRAPH_ENTITY_SUMMARY_ENABLED=false   # LLM summaries (expensive, off by default)
GRAPH_STALE_GRACE_DAYS=7             # days before pruning stale entries
```

---

## Dependencies on Other Systems

- **Neo4j** must be running (already in `start_services.sh`)
- **LLM client** needed for entity summaries (reuse existing `create_llm_client`)
- **data_module orchestrator** for incremental record selection
- **Redis** (optional) for distributed locking if multiple workers

## Priority Order

1. Incremental ingest (highest value — avoids full reprocess)
2. Periodic scheduler (enables automation)
3. Neighborhood precompute (biggest query-time speedup)
4. Health monitoring (observability)
5. Entity summary cache (nice-to-have, expensive)
6. Stale pruning (needed for long-running production)
