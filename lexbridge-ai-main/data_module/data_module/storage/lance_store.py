"""
LanceDB store — hot vector index for fast semantic RAG retrieval.

Stores ChunkRecords with dense embeddings in a LanceDB table.
Supports ANN search, scalar metadata filtering, and hybrid BM25+dense search.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..schema.chunk import ChunkRecord
from .base import AbstractStore

logger = logging.getLogger(__name__)


class LanceStore(AbstractStore):
    """
    Wraps a LanceDB table for vector + metadata storage and retrieval.

    The table is created lazily on first write with the schema inferred from
    the first batch of ChunkRecords.
    """

    def __init__(
        self,
        db_path: Path,
        table_name: str = "chunks",
        metric: str = "cosine",
    ) -> None:
        db_path.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.table_name = table_name
        self.metric = metric
        self._db = None
        self._table = None

    def _get_db(self):
        if self._db is None:
            import lancedb
            self._db = lancedb.connect(str(self.db_path))
        return self._db

    def _get_or_create_table(self, sample_row: dict | None = None):
        db = self._get_db()
        existing = db.table_names()
        if self.table_name in existing:
            if self._table is None:
                self._table = db.open_table(self.table_name)
        elif sample_row is not None:
            import pyarrow as pa
            schema = _infer_schema(sample_row)
            self._table = db.create_table(self.table_name, schema=schema)
        return self._table

    def upsert_chunks(self, chunks: list[ChunkRecord]) -> None:
        """Insert or overwrite chunks in the LanceDB table."""
        if not chunks:
            return

        rows = [c.to_lance_row() for c in chunks]
        # Filter out chunks with no embedding
        rows = [r for r in rows if r.get("vector") is not None]
        if not rows:
            logger.warning("LanceStore: no embedded chunks to write (embeddings missing?)")
            return

        table = self._get_or_create_table(rows[0])
        if table is None:
            logger.error("LanceStore: could not open or create table.")
            return

        table.add(rows, mode="append")
        logger.debug("LanceStore: added %d rows.", len(rows))

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        ANN vector search.

        Args:
            query_vector: dense embedding of the query.
            top_k: number of results to return.
            filters: SQL-style filter string, e.g. "meta_source = 'stackexchange'".
        """
        table = self._get_or_create_table()
        if table is None:
            return []

        search = table.search(query_vector).limit(top_k).metric(self.metric)
        if filters:
            search = search.where(filters)
        return search.to_list()

    def create_index(
        self,
        index_type: str = "IVF_PQ",
        num_partitions: int = 256,
        num_sub_vectors: int = 96,
        *,
        replace: bool = True,
    ) -> None:
        """
        Create an ANN index for fast retrieval. Run after bulk load.

        Args:
            index_type: "IVF_PQ" (default, compact) or "HNSW_SQ" (faster search,
                        larger index). LanceDB 0.20+ supports both.
            num_partitions: IVF partitions (IVF_PQ only).
            num_sub_vectors: PQ sub-vectors (IVF_PQ only).
            replace: if True, drop any existing index first.
        """
        table = self._get_or_create_table()
        if table is None:
            return

        idx_type = index_type.upper().replace("-", "_")

        if idx_type == "HNSW_SQ":
            try:
                from lancedb.index import HnswSq
                table.create_index(
                    "vector",
                    config=HnswSq(m=16, ef_construction=150),
                    metric=self.metric,
                    replace=replace,
                )
                logger.info(
                    "LanceDB: HNSW-SQ index created on table '%s'.", self.table_name
                )
                return
            except Exception as exc:
                logger.warning(
                    "HNSW-SQ index creation failed (%s), falling back to IVF-PQ.", exc
                )

        table.create_index(
            metric=self.metric,
            num_partitions=num_partitions,
            num_sub_vectors=num_sub_vectors,
            replace=replace,
        )
        logger.info("LanceDB: IVF-PQ index created on table '%s'.", self.table_name)

    def count(self) -> int:
        table = self._get_or_create_table()
        return len(table) if table is not None else 0

    def close(self) -> None:
        self._table = None
        self._db = None


def _infer_schema(sample_row: dict) -> "pa.Schema":
    """Infer a PyArrow schema from a sample LanceDB row dict."""
    import pyarrow as pa
    fields = []
    for k, v in sample_row.items():
        if k == "vector":
            if v is not None:
                fields.append(pa.field("vector", pa.list_(pa.float32(), len(v))))
            continue
        if isinstance(v, bool):
            fields.append(pa.field(k, pa.bool_()))
        elif isinstance(v, int):
            fields.append(pa.field(k, pa.int32()))
        elif isinstance(v, float):
            fields.append(pa.field(k, pa.float32()))
        else:
            fields.append(pa.field(k, pa.string()))
    return pa.schema(fields)
