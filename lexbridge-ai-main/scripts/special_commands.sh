#!/usr/bin/env bash
# ===========================================================================
# Special Commands — collected from the Neo4j graph migration session
# ===========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRJ="$(cd "$SCRIPT_DIR/.." && pwd)"
CSV_DIR="$PRJ/data_module/data/index/graph/neo4j_csv"
GRAPH_PKL="$PRJ/data_module/data/index/graph/graph.pkl.gz"
VENV="$PRJ/data_module/.venv/bin/activate"
NEO4J_PASSWORD="specialNeo123\$"

# ── 1. Kill the old (slow) Cypher-based export ──────────────────────────────
# kill 8920

# ── 2. Export NetworkX pickle → CSV for neo4j-admin ─────────────────────────
# ~16 min total (14 min pickle load + 2 min CSV write)
# Produces nodes.csv (1.4 GB) and relationships.csv (1.75 GB)
cd "$PRJ/data_module" && source "$VENV"
PYTHONUNBUFFERED=1 python scripts/export_to_neo4j_admin.py export-csv \
  --graph "$GRAPH_PKL" \
  --csv-dir "$CSV_DIR"

# ── 3. Stop Neo4j before bulk import ────────────────────────────────────────
neo4j stop

# ── 4. neo4j-admin bulk import (~32 seconds for 17.6M nodes + 20.9M edges) ─
# Key flags:
#   --multiline-fields=true   — some node descriptions contain newlines
#   --overwrite-destination    — replace existing neo4j database
#   --skip-duplicate-nodes     — deduplicate by entity_id:ID
#   --skip-bad-relationships   — skip edges referencing missing nodes
#   --id-type=string           — entity IDs are strings, not integers
/opt/homebrew/bin/neo4j-admin database import full \
  --additional-config=/opt/homebrew/Cellar/neo4j/2026.03.1/libexec/conf/neo4j.conf \
  --overwrite-destination=true \
  --skip-duplicate-nodes=true \
  --skip-bad-relationships=true \
  --multiline-fields=true \
  --id-type=string \
  --threads=7 \
  --nodes "$CSV_DIR/nodes.csv" \
  --relationships "$CSV_DIR/relationships.csv"

# ── 5. Start Neo4j ──────────────────────────────────────────────────────────
neo4j start
sleep 10   # wait for bolt port

# ── 6. Create indexes ───────────────────────────────────────────────────────
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', '$NEO4J_PASSWORD'))
with driver.session() as s:
    s.run('CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE')
    s.run('CREATE INDEX entity_type_idx IF NOT EXISTS FOR (n:Entity) ON (n.entity_type)')
    s.run('CREATE INDEX entity_label_idx IF NOT EXISTS FOR (n:Entity) ON (n.label)')
    print('Indexes created.')
driver.close()
"

# ── 7. Verify the import ────────────────────────────────────────────────────
python3 -c "
from neo4j import GraphDatabase
import time
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', '$NEO4J_PASSWORD'))
with driver.session() as s:
    nodes = s.run('MATCH (n) RETURN count(n) as c').single()['c']
    edges = s.run('MATCH ()-[r]->() RETURN count(r) as c').single()['c']
    print(f'Nodes: {nodes:,}')
    print(f'Edges: {edges:,}')
with driver.session() as s:
    result = s.run('MATCH (n:Entity) RETURN n.entity_type AS t, count(*) AS c ORDER BY c DESC LIMIT 10')
    print('Entity types:')
    for r in result:
        print(f'  {r[\"t\"]}: {r[\"c\"]:,}')
driver.close()
"

# ── 8. One-shot command (export + import in one go) ─────────────────────────
# cd "$PRJ/data_module" && source "$VENV"
# PYTHONUNBUFFERED=1 python scripts/export_to_neo4j_admin.py all

# ===========================================================================
# Useful diagnostic commands used during the session
# ===========================================================================

# Check if Neo4j is running
# neo4j status
# lsof -nP -iTCP:7687 -sTCP:LISTEN

# Check neo4j-admin version
# neo4j-admin --version

# Check Neo4j database info
# /opt/homebrew/bin/neo4j-admin database info neo4j

# Check process status of export script
# pgrep -f "export_to_neo4j" | xargs -I{} ps -p {} -o pid,rss,%mem,%cpu,etime

# Check if export process has TCP connection to Neo4j
# lsof -nP -p <PID> | grep TCP

# Inspect Neo4j data directory
# ls /opt/homebrew/var/neo4j/data/databases/

# Check Neo4j conf for data directory
# cat /opt/homebrew/Cellar/neo4j/2026.03.1/libexec/conf/neo4j.conf | grep "directories"

# Check CSV file sizes
# ls -lh "$CSV_DIR"

# Quick Cypher queries via Python
# python3 -c "
# from neo4j import GraphDatabase
# d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', '$NEO4J_PASSWORD'))
# with d.session() as s:
#     print(s.run('MATCH (n) RETURN count(n)').single()[0])
# d.close()
# "
