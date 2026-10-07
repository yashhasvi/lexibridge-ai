"""
Fast export: NetworkX pickle → CSV → neo4j-admin database import full.

10-100x faster than Cypher MERGE batches for large graphs.

Usage
─────
  # Step 1: Export CSVs (requires loading the pickle, ~14 min for 1.1GB)
  python scripts/export_to_neo4j_admin.py export-csv

  # Step 2: Import into Neo4j (requires Neo4j to be stopped first)
  python scripts/export_to_neo4j_admin.py import

  # Or do both in one shot:
  python scripts/export_to_neo4j_admin.py all
"""
from __future__ import annotations

import argparse
import csv
import gzip
import logging
import os
import pickle
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

DEFAULT_GRAPH = "data/index/graph/graph.pkl.gz"
DEFAULT_CSV_DIR = "data/index/graph/neo4j_csv"


def export_csv(graph_path: Path, csv_dir: Path) -> tuple[Path, Path]:
    """Stream the pickle graph to CSV files for neo4j-admin import."""
    csv_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = csv_dir / "nodes.csv"
    rels_path = csv_dir / "relationships.csv"

    logger.info("Loading graph from %s …", graph_path)
    t0 = time.time()
    with gzip.open(graph_path, "rb") as f:
        g = pickle.load(f)
    logger.info(
        "Graph loaded in %.1fs — %d nodes, %d edges",
        time.time() - t0, g.number_of_nodes(), g.number_of_edges(),
    )

    # ── Write nodes CSV ───────────────────────────────────────────────────
    logger.info("Writing nodes to %s …", nodes_path)
    t1 = time.time()
    total_nodes = g.number_of_nodes()
    with open(nodes_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["entity_id:ID", "label", "entity_type", "description", ":LABEL"])
        for i, (node_id, data) in enumerate(g.nodes(data=True)):
            writer.writerow([
                node_id,
                (data.get("label") or str(node_id))[:200],
                (data.get("entity_type") or "unknown")[:80],
                (data.get("description") or "")[:400],
                "Entity",
            ])
            if (i + 1) % 1_000_000 == 0:
                elapsed = time.time() - t1
                logger.info(
                    "  nodes %d / %d  (%.0f/s, %.0f%% done)",
                    i + 1, total_nodes, (i + 1) / elapsed, 100 * (i + 1) / total_nodes,
                )
    logger.info("Nodes CSV done in %.1fs (%d rows)", time.time() - t1, total_nodes)

    # ── Write relationships CSV ───────────────────────────────────────────
    logger.info("Writing relationships to %s …", rels_path)
    t2 = time.time()
    total_edges = g.number_of_edges()
    seen: set[str] = set()
    written = 0
    with open(rels_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([":START_ID", ":END_ID", "triple_id", "predicate", ":TYPE"])
        for i, (u, v, key, data) in enumerate(g.edges(data=True, keys=True)):
            triple_id = str(key)
            if triple_id in seen:
                continue
            seen.add(triple_id)
            writer.writerow([
                u,
                v,
                triple_id,
                (data.get("predicate") or "RELATED_TO")[:120],
                "RELATION",
            ])
            written += 1
            if (i + 1) % 1_000_000 == 0:
                elapsed = time.time() - t2
                logger.info(
                    "  edges scanned %d / %d  (%.0f/s, written %d)",
                    i + 1, total_edges, (i + 1) / elapsed, written,
                )
    logger.info("Relationships CSV done in %.1fs (%d rows)", time.time() - t2, written)

    node_size = nodes_path.stat().st_size / 1024 / 1024
    rel_size = rels_path.stat().st_size / 1024 / 1024
    logger.info("CSV files: nodes=%.0f MB, relationships=%.0f MB", node_size, rel_size)
    logger.info("Total export time: %.1fs", time.time() - t0)
    return nodes_path, rels_path


def run_import(csv_dir: Path, database: str = "neo4j") -> None:
    """Stop Neo4j, run neo4j-admin import, start Neo4j."""
    nodes_path = csv_dir / "nodes.csv"
    rels_path = csv_dir / "relationships.csv"

    if not nodes_path.exists() or not rels_path.exists():
        logger.error("CSV files not found in %s. Run 'export-csv' first.", csv_dir)
        sys.exit(1)

    logger.info("Stopping Neo4j …")
    subprocess.run(["neo4j", "stop"], check=False)
    time.sleep(3)

    logger.info("Running neo4j-admin database import full …")
    cmd = [
        "neo4j-admin", "database", "import", "full",
        "--additional-config=/opt/homebrew/Cellar/neo4j/2026.03.1/libexec/conf/neo4j.conf",
        "--overwrite-destination=true",
        "--skip-duplicate-nodes=true",
        "--skip-bad-relationships=true",
        "--multiline-fields=true",
        "--id-type=string",
        "--threads", str(max(1, (os.cpu_count() or 4) - 1)),
        "--nodes", str(nodes_path),
        "--relationships", str(rels_path),
    ]
    logger.info("  %s", " ".join(str(c) for c in cmd))
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        logger.error("neo4j-admin import failed (exit code %d)", result.returncode)
        sys.exit(1)
    logger.info("Import completed in %.1fs", time.time() - t0)

    logger.info("Starting Neo4j …")
    subprocess.run(["neo4j", "start"], check=True)

    logger.info("Waiting for Neo4j to come online …")
    for attempt in range(60):
        time.sleep(2)
        try:
            from neo4j import GraphDatabase
            password = os.getenv("NEO4J_PASSWORD", "specialNeo123$")
            driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", password))
            with driver.session() as session:
                count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
                logger.info("Neo4j online — %d nodes loaded", count)
            driver.close()
            break
        except Exception:
            if attempt % 5 == 0:
                logger.info("  … waiting (%d/60)", attempt)
    else:
        logger.warning("Timed out waiting for Neo4j. Check 'neo4j status'.")
        return

    create_indexes()


def create_indexes() -> None:
    """Create indexes for fast lookups after import."""
    from neo4j import GraphDatabase
    password = os.getenv("NEO4J_PASSWORD", "specialNeo123$")
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", password))
    with driver.session() as session:
        session.run("CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE")
        session.run("CREATE INDEX entity_type_idx IF NOT EXISTS FOR (n:Entity) ON (n.entity_type)")
        session.run("CREATE INDEX entity_label_idx IF NOT EXISTS FOR (n:Entity) ON (n.label)")
    driver.close()
    logger.info("Indexes created.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Fast graph export via neo4j-admin import")
    ap.add_argument("action", choices=["export-csv", "import", "all"],
                    help="'export-csv' = pickle → CSV; 'import' = CSV → Neo4j; 'all' = both")
    ap.add_argument("--graph", default=DEFAULT_GRAPH)
    ap.add_argument("--csv-dir", default=DEFAULT_CSV_DIR)
    ap.add_argument("--database", default="neo4j")
    args = ap.parse_args()

    csv_dir = Path(args.csv_dir)

    if args.action in ("export-csv", "all"):
        export_csv(Path(args.graph), csv_dir)

    if args.action in ("import", "all"):
        run_import(csv_dir, args.database)

    logger.info("Done.")


if __name__ == "__main__":
    main()
