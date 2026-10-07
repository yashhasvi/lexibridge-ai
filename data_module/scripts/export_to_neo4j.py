"""
Export the NetworkX graph (graph.pkl.gz) to Neo4j.

Two modes
─────────
  --mode sample   (default) Export the top-N most-connected nodes + their
                  mutual edges.  Fast (~5 min), great for Neo4j Browser.
  --mode full     Export every node and edge.  Needs ~10 GB RAM and 1–2 h.

Usage
─────
  # Quick visualisation sample (top 20 000 nodes)
  python scripts/export_to_neo4j.py --wipe

  # Larger sample
  python scripts/export_to_neo4j.py --wipe --top-n 50000

  # Full graph
  python scripts/export_to_neo4j.py --wipe --mode full
"""
from __future__ import annotations

import argparse
import gzip
import logging
import pickle
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def _setup(session) -> None:
    session.run(
        "CREATE CONSTRAINT entity_id IF NOT EXISTS "
        "FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE"
    )
    session.run(
        "CREATE INDEX entity_type IF NOT EXISTS "
        "FOR (n:Entity) ON (n.entity_type)"
    )
    session.run(
        "CREATE INDEX entity_label IF NOT EXISTS "
        "FOR (n:Entity) ON (n.label)"
    )


def _import_nodes(driver, nodes: list, batch_size: int) -> None:
    logger.info("Importing %d nodes …", len(nodes))
    count = 0
    t0 = time.time()
    with driver.session() as session:
        for batch in _chunks(nodes, batch_size):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (e:Entity {entity_id: row.entity_id})
                SET e.label       = row.label,
                    e.entity_type = row.entity_type,
                    e.degree      = row.degree,
                    e.description = row.description
                """,
                rows=batch,
            )
            count += len(batch)
            if count % 20_000 == 0:
                logger.info("  nodes %d / %d  (%.0f/s)", count, len(nodes),
                            count / (time.time() - t0))
    logger.info("Nodes done in %.1fs", time.time() - t0)


def _import_edges(driver, edges: list, batch_size: int) -> None:
    logger.info("Importing %d edges …", len(edges))
    count = 0
    t0 = time.time()
    with driver.session() as session:
        for batch in _chunks(edges, batch_size):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (s:Entity {entity_id: row.subject_id})
                MATCH (o:Entity {entity_id: row.object_id})
                MERGE (s)-[r:RELATION {triple_id: row.triple_id}]->(o)
                SET r.predicate = row.predicate
                """,
                rows=batch,
            )
            count += len(batch)
            if count % 50_000 == 0:
                logger.info("  edges %d / %d  (%.0f/s)", count, len(edges),
                            count / (time.time() - t0))
    logger.info("Edges done in %.1fs", time.time() - t0)


def export(
    graph_path: Path,
    uri: str,
    user: str,
    password: str,
    batch_size: int = 2000,
    wipe: bool = False,
    mode: str = "sample",
    top_n: int = 20_000,
) -> None:
    from neo4j import GraphDatabase

    logger.info("Loading graph from %s …", graph_path)
    t0 = time.time()
    with gzip.open(graph_path, "rb") as f:
        g = pickle.load(f)
    logger.info(
        "Graph loaded in %.1fs — %d nodes, %d edges",
        time.time() - t0, g.number_of_nodes(), g.number_of_edges(),
    )

    # ── Select node set ──────────────────────────────────────────────────────
    if mode == "sample":
        logger.info("Sample mode: selecting top %d nodes by degree …", top_n)
        ranked = sorted(g.degree(), key=lambda x: x[1], reverse=True)[:top_n]
        node_ids = {n for n, _ in ranked}
        logger.info("  %d nodes selected", len(node_ids))
    else:
        node_ids = set(g.nodes())

    # ── Build payload ────────────────────────────────────────────────────────
    total_nodes = len(node_ids)
    logger.info("Building node payload (%d nodes) …", total_nodes)
    t_payload = time.time()
    nodes = []
    for i, node_id in enumerate(node_ids):
        data = g.nodes[node_id]
        nodes.append({
            "entity_id": node_id,
            "label":       (data.get("label") or str(node_id))[:200],
            "entity_type": (data.get("entity_type") or "unknown")[:80],
            "degree":      g.degree(node_id),
            "description": (data.get("description") or "")[:400],
        })
        if (i + 1) % 1_000_000 == 0:
            logger.info("  nodes %d / %d  (%.0f/s)", i + 1, total_nodes,
                        (i + 1) / (time.time() - t_payload))
    logger.info("Node payload built in %.1fs", time.time() - t_payload)

    total_edges = g.number_of_edges()
    logger.info("Building edge payload (%d edges) …", total_edges)
    t_edges = time.time()
    edges = []
    seen_edges: set[str] = set()
    edge_count = 0
    for u, v, key, data in g.edges(data=True, keys=True):
        edge_count += 1
        if u not in node_ids or v not in node_ids:
            continue
        triple_id = str(key)
        if triple_id in seen_edges:
            continue
        seen_edges.add(triple_id)
        edges.append({
            "triple_id":  triple_id,
            "subject_id": u,
            "object_id":  v,
            "predicate":  (data.get("predicate") or "RELATED_TO")[:120],
        })
        if edge_count % 1_000_000 == 0:
            logger.info("  edges scanned %d / %d  (%.0f/s)", edge_count, total_edges,
                        edge_count / (time.time() - t_edges))
    logger.info("Edge payload built in %.1fs", time.time() - t_edges)

    logger.info("Payload: %d nodes, %d edges", len(nodes), len(edges))

    # ── Connect and import ───────────────────────────────────────────────────
    driver = GraphDatabase.driver(uri, auth=(user, password))

    with driver.session() as session:
        _setup(session)
        if wipe:
            logger.warning("--wipe: deleting all existing data …")
            session.run("MATCH (n) DETACH DELETE n")

    _import_nodes(driver, nodes, batch_size)
    _import_edges(driver, edges, batch_size)

    logger.info("Export complete in %.1fs total", time.time() - t0)
    driver.close()

    print("\n── Done ────────────────────────────────────────────────────────")
    print(f"  {len(nodes):>10,} nodes imported")
    print(f"  {len(edges):>10,} edges imported")
    print()
    print("Open Neo4j Browser at http://localhost:7474")
    print("Useful starter queries:")
    print()
    print("  -- Most connected nodes")
    print("  MATCH (n:Entity) RETURN n ORDER BY n.degree DESC LIMIT 50")
    print()
    print("  -- Explore a node and its neighbours")
    print("  MATCH (n:Entity {label:'United States'})-[r]-(m) RETURN n,r,m LIMIT 100")
    print()
    print("  -- All entity types")
    print("  MATCH (n:Entity) RETURN DISTINCT n.entity_type, count(*) ORDER BY count(*) DESC")
    print()
    print("  -- Shortest path between two entities")
    print("  MATCH p=shortestPath((a:Entity {label:'Python'})-[*]-(b:Entity {label:'JavaScript'}))")
    print("  RETURN p")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="data/index/graph/graph.pkl.gz")
    ap.add_argument("--uri", default="bolt://localhost:7687")
    ap.add_argument("--user", default="neo4j")
    ap.add_argument("--password", default="specialNeo123$")
    ap.add_argument("--batch-size", type=int, default=2000)
    ap.add_argument("--mode", choices=["sample", "full"], default="sample",
                    help="'sample' = top-N by degree (fast); 'full' = everything (slow)")
    ap.add_argument("--top-n", type=int, default=20_000,
                    help="Number of nodes to include in sample mode (default 20000)")
    ap.add_argument("--wipe", action="store_true",
                    help="Delete ALL existing Neo4j data before import (irreversible)")
    args = ap.parse_args()

    export(
        graph_path=Path(args.graph),
        uri=args.uri,
        user=args.user,
        password=args.password,
        batch_size=args.batch_size,
        wipe=args.wipe,
        mode=args.mode,
        top_n=args.top_n,
    )


if __name__ == "__main__":
    main()
