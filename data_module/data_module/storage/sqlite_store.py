"""
SQLite store — lightweight state management for the pipeline.

Tracks:
  - Pipeline run history (source, start/end time, record counts)
  - source_id → canonical_id mapping (for cross-source dedup and link resolution)
  - Download status per source file
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import AbstractStore

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    records_in   INTEGER DEFAULT 0,
    records_out  INTEGER DEFAULT 0,
    status       TEXT DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS source_id_map (
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    canonical_id  TEXT NOT NULL,
    ingested_at   TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (source, source_id)
);

CREATE TABLE IF NOT EXISTS seen_hashes (
    content_hash  TEXT PRIMARY KEY,
    source        TEXT,
    canonical_id  TEXT,
    ingested_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS download_status (
    source        TEXT NOT NULL,
    filename      TEXT NOT NULL,
    status        TEXT NOT NULL,  -- 'pending' | 'downloading' | 'done' | 'error'
    size_bytes    INTEGER,
    downloaded_at TEXT,
    PRIMARY KEY (source, filename)
);

-- Watermark table for incremental ingestion.
-- After each successful pipeline run we record how far we got so the next
-- run can skip rows already seen (row-based watermark) or detect a new
-- upstream dataset version (version-based watermark).
CREATE TABLE IF NOT EXISTS source_checkpoints (
    source_name      TEXT PRIMARY KEY,
    rows_ingested    INTEGER DEFAULT 0,   -- total canonical rows written so far
    dataset_version  TEXT,                -- HF commit hash / archive URL / dump date
    max_rows_config  INTEGER,             -- max_rows setting used at ingest time
    last_ingested_at TEXT,                -- UTC ISO timestamp of last successful run
    status           TEXT DEFAULT 'complete',  -- 'complete' | 'partial' | 'failed'
    extra_json       TEXT                 -- JSON blob for source-specific metadata
);
"""


class SQLiteStore(AbstractStore):
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_DDL)
        self._conn.commit()

    def start_run(self, source: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO pipeline_runs (source, started_at) VALUES (?, ?)",
            (source, datetime.utcnow().isoformat()),
        )
        self._conn.commit()
        return cur.lastrowid

    def finish_run(
        self, run_id: int, records_in: int, records_out: int, status: str = "done"
    ) -> None:
        self._conn.execute(
            "UPDATE pipeline_runs SET finished_at=?, records_in=?, records_out=?, status=? WHERE run_id=?",
            (datetime.utcnow().isoformat(), records_in, records_out, status, run_id),
        )
        self._conn.commit()

    def get_canonical_id(self, source: str, source_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT canonical_id FROM source_id_map WHERE source=? AND source_id=?",
            (source, source_id),
        ).fetchone()
        return row["canonical_id"] if row else None

    def mark_download(self, source: str, filename: str, status: str, size_bytes: int | None = None) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO download_status (source, filename, status, size_bytes, downloaded_at)
               VALUES (?, ?, ?, ?, ?)""",
            (source, filename, status, size_bytes, datetime.utcnow().isoformat() if status == "done" else None),
        )
        self._conn.commit()

    def get_run_history(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM pipeline_runs ORDER BY run_id DESC LIMIT 50"
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Checkpoint API (incremental ingestion watermarks)
    # ------------------------------------------------------------------

    def write_checkpoint(
        self,
        source_name: str,
        rows_ingested: int,
        dataset_version: str | None = None,
        max_rows_config: int | None = None,
        status: str = "complete",
        extra: dict | None = None,
    ) -> None:
        import json
        self._conn.execute(
            """INSERT OR REPLACE INTO source_checkpoints
               (source_name, rows_ingested, dataset_version, max_rows_config,
                last_ingested_at, status, extra_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                source_name,
                rows_ingested,
                dataset_version,
                max_rows_config,
                datetime.utcnow().isoformat(),
                status,
                json.dumps(extra) if extra else None,
            ),
        )
        self._conn.commit()

    def get_checkpoint(self, source_name: str) -> dict[str, Any] | None:
        import json
        row = self._conn.execute(
            "SELECT * FROM source_checkpoints WHERE source_name = ?",
            (source_name,),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        if result.get("extra_json"):
            result["extra"] = json.loads(result["extra_json"])
        return result

    def get_all_checkpoints(self) -> list[dict[str, Any]]:
        import json
        rows = self._conn.execute(
            "SELECT * FROM source_checkpoints ORDER BY source_name"
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            if d.get("extra_json"):
                d["extra"] = json.loads(d["extra_json"])
            results.append(d)
        return results

    def close(self) -> None:
        if self._conn:
            self._conn.commit()
            self._conn.close()
