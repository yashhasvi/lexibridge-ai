"""
Parquet store — cold archive for CanonicalQA and ChunkRecord.

Partitioned by source + year for efficient filtered reads.
Uses PyArrow for schema-enforced writes and predicate pushdown reads.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Generator, Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from ..schema.canonical import CanonicalQA
from ..schema.chunk import ChunkRecord
from .base import AbstractStore

logger = logging.getLogger(__name__)

# Arrow schema for CanonicalQA rows (flattened; nested lists stored as JSON strings)
_CANONICAL_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("source", pa.string()),
    pa.field("source_id", pa.string()),
    pa.field("site", pa.string()),
    pa.field("title", pa.string()),
    pa.field("body", pa.string()),
    pa.field("accepted_answer_id", pa.string()),
    pa.field("tags", pa.string()),        # JSON list
    pa.field("language", pa.string()),
    pa.field("score", pa.int32()),
    pa.field("view_count", pa.int32()),
    pa.field("answer_count", pa.int32()),
    pa.field("created_at", pa.string()),
    pa.field("source_url", pa.string()),
    pa.field("license", pa.string()),
    pa.field("content_hash", pa.string()),
    pa.field("answers_json", pa.string()),  # JSON list of CanonicalAnswer dicts
    pa.field("year", pa.int32()),
])

_CHUNK_SCHEMA = pa.schema([
    pa.field("chunk_id", pa.string()),
    pa.field("parent_question_id", pa.string()),
    pa.field("parent_answer_id", pa.string()),
    pa.field("chunk_type", pa.string()),
    pa.field("text", pa.string()),
    pa.field("token_count", pa.int32()),
    pa.field("meta_source", pa.string()),
    pa.field("meta_site", pa.string()),
    pa.field("meta_language", pa.string()),
    pa.field("meta_tags", pa.string()),
    pa.field("meta_score", pa.int32()),
    pa.field("meta_has_accepted_answer", pa.bool_()),
    pa.field("meta_license", pa.string()),
    pa.field("meta_source_url", pa.string()),
    pa.field("meta_year", pa.int32()),
    pa.field("meta_embedding_model", pa.string()),
    pa.field("source", pa.string()),   # partition key
    pa.field("year", pa.int32()),      # partition key
])


class ParquetStore(AbstractStore):
    """
    Writes CanonicalQA and ChunkRecord streams to partitioned Parquet files.

    Directory layout:
        canonical/source=stackexchange/year=2024/part-0001.parquet
        chunks/source=stackexchange/year=2024/part-0001.parquet
    """

    def __init__(
        self,
        canonical_dir: Path,
        chunks_dir: Path,
        partition_cols: list[str] | None = None,
        compression: str = "zstd",
        row_group_size: int = 10_000,
    ) -> None:
        self.canonical_dir = canonical_dir
        self.chunks_dir = chunks_dir
        self.partition_cols = partition_cols or ["source", "year"]
        self.compression = compression
        self.row_group_size = row_group_size
        canonical_dir.mkdir(parents=True, exist_ok=True)
        chunks_dir.mkdir(parents=True, exist_ok=True)

    def write_canonical(
        self,
        records: Iterator[CanonicalQA],
        source_name: str,
        batch_size: int = 10_000,
    ) -> None:
        """Write CanonicalQA records to partitioned Parquet."""
        import json
        rows: list[dict] = []
        written = 0

        for record in records:
            year = record.created_at.year if record.created_at else 0
            rows.append({
                "id": record.id,
                "source": record.source.value,
                "source_id": record.source_id,
                "site": record.site or "",
                "title": record.title,
                "body": record.body,
                "accepted_answer_id": record.accepted_answer_id or "",
                "tags": json.dumps(record.tags),
                "language": record.language,
                "score": record.score,
                "view_count": record.view_count or 0,
                "answer_count": record.answer_count,
                "created_at": record.created_at.isoformat() if record.created_at else "",
                "source_url": record.source_url or "",
                "license": record.license.value,
                "content_hash": record.content_hash,
                "answers_json": json.dumps([a.model_dump(mode="json", exclude={"body_html"}) for a in record.answers]),
                "year": year,
            })
            if len(rows) >= batch_size:
                self._flush_canonical(rows, source_name)
                written += len(rows)
                rows = []

        if rows:
            self._flush_canonical(rows, source_name)
            written += len(rows)

        logger.info("ParquetStore: wrote %d canonical records for %s", written, source_name)

    def _flush_canonical(self, rows: list[dict], source_name: str) -> None:
        table = pa.Table.from_pylist(rows, schema=_CANONICAL_SCHEMA)
        pq.write_to_dataset(
            table,
            root_path=str(self.canonical_dir),
            partition_cols=self.partition_cols,
            compression=self.compression,
            existing_data_behavior="overwrite_or_ignore",
        )

    def write_chunks(
        self,
        chunks: Iterator[ChunkRecord],
        source_name: str,
        batch_size: int = 10_000,
    ) -> None:
        """Write ChunkRecords (without embeddings) to partitioned Parquet."""
        rows: list[dict] = []
        written = 0

        for chunk in chunks:
            m = chunk.metadata
            rows.append({
                "chunk_id": chunk.chunk_id,
                "parent_question_id": chunk.parent_question_id,
                "parent_answer_id": chunk.parent_answer_id or "",
                "chunk_type": chunk.chunk_type.value,
                "text": chunk.text,
                "token_count": chunk.token_count,
                "meta_source": m.source.value,
                "meta_site": m.site or "",
                "meta_language": m.language,
                "meta_tags": ",".join(m.tags),
                "meta_score": m.score,
                "meta_has_accepted_answer": m.has_accepted_answer,
                "meta_license": m.license.value,
                "meta_source_url": m.source_url or "",
                "meta_year": m.year or 0,
                "meta_embedding_model": m.embedding_model or "",
                "source": m.source.value,
                "year": m.year or 0,
            })
            if len(rows) >= batch_size:
                self._flush_chunks(rows)
                written += len(rows)
                rows = []

        if rows:
            self._flush_chunks(rows)
            written += len(rows)

        logger.info("ParquetStore: wrote %d chunk records for %s", written, source_name)

    def _flush_chunks(self, rows: list[dict]) -> None:
        table = pa.Table.from_pylist(rows, schema=_CHUNK_SCHEMA)
        pq.write_to_dataset(
            table,
            root_path=str(self.chunks_dir),
            partition_cols=self.partition_cols,
            compression=self.compression,
            existing_data_behavior="overwrite_or_ignore",
        )

    def read_canonical(
        self,
        source: str | None = None,
        year: int | None = None,
        filters: list | None = None,
    ) -> pa.Table:
        """Read canonical Parquet with optional partition filters."""
        f = filters or []
        if source:
            f.append(("source", "=", source))
        if year:
            f.append(("year", "=", year))
        return pq.read_table(str(self.canonical_dir), filters=f or None)

    def read_chunks(
        self,
        source: str | None = None,
        year: int | None = None,
        filters: list | None = None,
    ) -> pa.Table:
        f = filters or []
        if source:
            f.append(("source", "=", source))
        if year:
            f.append(("year", "=", year))
        return pq.read_table(str(self.chunks_dir), filters=f or None)

    def close(self) -> None:
        pass
