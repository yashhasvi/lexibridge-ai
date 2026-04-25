"""
Graph store — dual-backend adapter: NetworkX (dev/small) or Neo4j (production).

NetworkX backend:
  - In-process directed multigraph
  - Persisted as gzipped pickle
  - Suitable for datasets up to ~5M nodes / ~20M edges

Neo4j backend:
  - Full property graph DB
  - Supports Cypher queries, complex traversals, large-scale
  - Requires running Neo4j instance
"""
from __future__ import annotations

import gzip
import logging
import pickle
from pathlib import Path
from typing import Any

from ..schema.graph import Entity, SubGraph, Triple
from .base import AbstractStore

logger = logging.getLogger(__name__)


class NetworkXGraphStore(AbstractStore):
    """Lightweight in-process graph backed by NetworkX."""

    def __init__(self, graph_path: Path) -> None:
        import networkx as nx
        self.graph_path = graph_path
        graph_path.parent.mkdir(parents=True, exist_ok=True)

        if graph_path.exists():
            logger.info("Loading graph from %s…", graph_path)
            with gzip.open(graph_path, "rb") as f:
                self._g: nx.MultiDiGraph = pickle.load(f)
        else:
            self._g = nx.MultiDiGraph()

    def upsert_entities(self, entities: list[Entity]) -> None:
        for ent in entities:
            attrs = {
                **ent.properties,              # base — may contain overlapping keys
                "entity_type": ent.entity_type,  # explicit fields always win
                "label": ent.label,
                "description": ent.description or "",
                "wikidata_id": ent.wikidata_id or "",
            }
            self._g.add_node(ent.entity_id, **attrs)

    def upsert_triples(self, triples: list[Triple]) -> None:
        for t in triples:
            attrs = {
                **t.properties,
                "predicate": t.predicate.value,
            }
            self._g.add_edge(
                t.subject_id,
                t.object_id,
                key=t.triple_id,
                **attrs,
            )

    def get_subgraph(self, entity_id: str, depth: int = 1) -> SubGraph:
        import networkx as nx
        if entity_id not in self._g:
            return SubGraph(seed_id=entity_id, depth=depth)

        # BFS up to `depth` hops
        visited = {entity_id}
        frontier = {entity_id}
        for _ in range(depth):
            next_frontier = set()
            for node in frontier:
                next_frontier.update(self._g.successors(node))
                next_frontier.update(self._g.predecessors(node))
            next_frontier -= visited
            visited.update(next_frontier)
            frontier = next_frontier

        entities = [
            Entity(
                entity_id=n,
                entity_type=self._g.nodes[n].get("entity_type", "unknown"),
                label=self._g.nodes[n].get("label", n),
            )
            for n in visited
        ]
        triples = []
        for u, v, k, data in self._g.edges(data=True, keys=True):
            if u in visited and v in visited:
                from ..schema.provenance import PredicateType
                pred_str = data.get("predicate", "RELATED_TO")
                try:
                    pred = PredicateType(pred_str)
                except ValueError:
                    pred = PredicateType.RELATED_TO
                triples.append(
                    Triple(
                        triple_id=k,
                        subject_id=u,
                        subject_type=self._g.nodes[u].get("entity_type", "unknown"),
                        predicate=pred,
                        object_id=v,
                        object_type=self._g.nodes[v].get("entity_type", "unknown"),
                        properties={kk: vv for kk, vv in data.items() if kk != "predicate"},
                    )
                )
        return SubGraph(seed_id=entity_id, entities=entities, triples=triples, depth=depth)

    def neighbors(self, entity_id: str) -> list[str]:
        return list(self._g.successors(entity_id)) + list(self._g.predecessors(entity_id))

    def save(self) -> None:
        logger.info("Saving graph to %s (%d nodes, %d edges)…", self.graph_path, self._g.number_of_nodes(), self._g.number_of_edges())
        with gzip.open(self.graph_path, "wb") as f:
            pickle.dump(self._g, f)

    def close(self) -> None:
        self.save()


class Neo4jGraphStore(AbstractStore):
    """Production graph store backed by Neo4j."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        from neo4j import GraphDatabase
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._ensure_constraints()
        logger.info("Neo4jGraphStore connected to %s", uri)

    def _ensure_constraints(self) -> None:
        with self._driver.session() as session:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE")
            session.run("CREATE INDEX entity_type_idx IF NOT EXISTS FOR (n:Entity) ON (n.entity_type)")

    def upsert_entities(self, entities: list[Entity]) -> None:
        with self._driver.session() as session:
            session.run(
                """
                UNWIND $rows AS row
                MERGE (e:Entity {entity_id: row.entity_id})
                SET e.label = row.label,
                    e.entity_type = row.entity_type,
                    e.wikidata_id = row.wikidata_id
                """,
                rows=[
                    {
                        "entity_id": e.entity_id,
                        "label": e.label,
                        "entity_type": e.entity_type,
                        "wikidata_id": e.wikidata_id or "",
                    }
                    for e in entities
                ],
            )

    def upsert_triples(self, triples: list[Triple]) -> None:
        with self._driver.session() as session:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (s:Entity {entity_id: row.subject_id})
                MATCH (o:Entity {entity_id: row.object_id})
                MERGE (s)-[r:RELATION {triple_id: row.triple_id}]->(o)
                SET r.predicate = row.predicate
                """,
                rows=[
                    {
                        "triple_id": t.triple_id,
                        "subject_id": t.subject_id,
                        "object_id": t.object_id,
                        "predicate": t.predicate.value,
                    }
                    for t in triples
                ],
            )

    def get_subgraph(self, entity_id: str, depth: int = 1) -> SubGraph:
        from ..schema.provenance import PredicateType

        depth = min(depth, 3)
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH path = (seed:Entity {entity_id: $eid})-[*1..""" + str(depth) + """]-()
                WITH path LIMIT 300
                UNWIND nodes(path) AS n
                UNWIND relationships(path) AS rel
                WITH collect(DISTINCT n) AS allNodes, collect(DISTINCT rel) AS allRels
                RETURN allNodes, allRels
                """,
                eid=entity_id,
            )
            record = result.single()
            entities: list[Entity] = []
            triples: list[Triple] = []

            if record is None:
                return SubGraph(seed_id=entity_id, depth=depth)

            for node in record["allNodes"]:
                nid = node.get("entity_id", "")
                if not nid:
                    continue
                entities.append(Entity(
                    entity_id=nid,
                    entity_type=node.get("entity_type", "unknown"),
                    label=node.get("label", nid),
                ))

            seen_rels: set[str] = set()
            for rel in record["allRels"]:
                tid = rel.get("triple_id", "")
                if not tid or tid in seen_rels:
                    continue
                seen_rels.add(tid)
                pred_str = rel.get("predicate", "RELATED_TO")
                try:
                    pred = PredicateType(pred_str)
                except ValueError:
                    pred = PredicateType.RELATED_TO

                start_id = rel.start_node.get("entity_id", "")
                end_id = rel.end_node.get("entity_id", "")
                triples.append(Triple(
                    triple_id=tid,
                    subject_id=start_id,
                    subject_type=rel.start_node.get("entity_type", "unknown"),
                    predicate=pred,
                    object_id=end_id,
                    object_type=rel.end_node.get("entity_type", "unknown"),
                ))

        return SubGraph(seed_id=entity_id, entities=entities, triples=triples, depth=depth)

    def neighbors(self, entity_id: str) -> list[str]:
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (e:Entity {entity_id: $eid})--(neighbor:Entity)
                RETURN neighbor.entity_id AS nid LIMIT 200
                """,
                eid=entity_id,
            )
            return [record["nid"] for record in result]

    def close(self) -> None:
        self._driver.close()


def get_graph_store(cfg: dict) -> AbstractStore:
    """Factory: return the correct graph store from config."""
    backend = cfg.get("backend", "networkx")
    if backend == "neo4j":
        return Neo4jGraphStore(
            uri=cfg["neo4j_uri"],
            user=cfg["neo4j_user"],
            password=cfg["neo4j_password"],
        )
    default_path = Path("./data/index/graph/graph.pkl.gz")
    return NetworkXGraphStore(Path(cfg.get("networkx_path", default_path)))
