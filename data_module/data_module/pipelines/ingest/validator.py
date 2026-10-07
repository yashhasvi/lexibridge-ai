"""
Ingest validator — validates CanonicalQA records and deduplicates by content_hash.

Two-level dedup:
  1. Exact dedup: SHA256 content_hash stored in SQLite; skip if seen.
  2. (Optional) Semantic dedup: embedding cosine similarity above threshold.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Generator

from pydantic import ValidationError

from ...schema.canonical import CanonicalQA

logger = logging.getLogger(__name__)


class IngestValidator:
    """
    Validates and deduplicates a stream of CanonicalQA records.

    Uses a SQLite database to track seen content_hash values across runs,
    so incremental ingestion never re-processes duplicate records.
    """

    def __init__(
        self,
        db_path: Path,
        dedup_exact: bool = True,
        min_text_length: int = 20,
    ) -> None:
        self.dedup_exact = dedup_exact
        self.min_text_length = min_text_length
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS seen_hashes (
                    content_hash TEXT PRIMARY KEY,
                    source TEXT,
                    canonical_id TEXT,
                    ingested_at TEXT DEFAULT (datetime('now'))
                )"""
            )
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS source_id_map (
                    source TEXT,
                    source_id TEXT,
                    canonical_id TEXT,
                    PRIMARY KEY (source, source_id)
                )"""
            )
            self._conn.commit()
        return self._conn

    def validate_and_dedup(
        self, records: Generator[CanonicalQA, None, None]
    ) -> Generator[CanonicalQA, None, None]:
        conn = self._get_conn()
        seen_hashes: set[str] = set()  # in-memory for current run (fast lookup)
        stats = {"total": 0, "invalid": 0, "too_short": 0, "duplicate": 0, "passed": 0}

        for record in records:
            stats["total"] += 1

            # Pydantic already validates on construction; re-check critical fields
            if not record.title or not record.title.strip():
                stats["invalid"] += 1
                continue

            text_len = len(record.title) + len(record.body)
            if text_len < self.min_text_length:
                stats["too_short"] += 1
                continue

            if self.dedup_exact:
                h = record.content_hash
                if h in seen_hashes:
                    stats["duplicate"] += 1
                    continue

                # Check persistent DB
                row = conn.execute(
                    "SELECT canonical_id FROM seen_hashes WHERE content_hash = ?", (h,)
                ).fetchone()
                if row:
                    stats["duplicate"] += 1
                    continue

                # Mark as seen
                seen_hashes.add(h)
                conn.execute(
                    "INSERT OR IGNORE INTO seen_hashes (content_hash, source, canonical_id) VALUES (?,?,?)",
                    (h, record.source.value, record.id),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO source_id_map (source, source_id, canonical_id) VALUES (?,?,?)",
                    (record.source.value, record.source_id, record.id),
                )
                if stats["passed"] % 5000 == 0:
                    conn.commit()

            stats["passed"] += 1
            yield record

        conn.commit()
        logger.info(
            "Validation stats: %s",
            " | ".join(f"{k}={v}" for k, v in stats.items()),
        )

    def close(self) -> None:
        if self._conn:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "IngestValidator":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
