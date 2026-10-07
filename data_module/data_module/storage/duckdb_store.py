"""
DuckDB store — fast SQL analytics over Parquet files.

Registers canonical and chunk Parquet datasets as virtual tables
so any SQL query can be run without loading everything into memory.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb

from .base import AbstractStore

logger = logging.getLogger(__name__)


class DuckDBStore(AbstractStore):
    """
    Wraps a DuckDB connection pointed at the Parquet archive.

    Use for:
      - Tag frequency analysis
      - Score distribution queries
      - Source coverage reports
      - Joining canonical records with chunk metadata
    """

    def __init__(
        self,
        db_path: Path,
        canonical_dir: Path,
        chunks_dir: Path,
        memory_limit: str = "4GB",
        threads: int = 4,
        read_only: bool = False,
    ) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._conn = duckdb.connect(str(db_path), read_only=read_only)
        self._conn.execute(f"SET memory_limit='{memory_limit}'")
        self._conn.execute(f"SET threads={threads}")
        # Register Parquet datasets as views
        self._register_views(canonical_dir, chunks_dir)

    def _register_views(self, canonical_dir: Path, chunks_dir: Path) -> None:
        for name, path in [("canonical", canonical_dir), ("chunks", chunks_dir)]:
            pattern = str(path / "**/*.parquet")
            try:
                self._conn.execute(
                    f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{pattern}', hive_partitioning=true)"
                )
                logger.debug("DuckDB: registered view '%s' → %s", name, pattern)
            except Exception as exc:
                logger.warning("DuckDB: could not register view '%s': %s", name, exc)

    def query(self, sql: str, params: list[Any] | None = None) -> "duckdb.DuckDBPyRelation":
        """Execute SQL and return a DuckDB relation (lazy, chainable)."""
        if params:
            return self._conn.execute(sql, params)
        return self._conn.execute(sql)

    def query_df(self, sql: str, params: list[Any] | None = None):
        """Execute SQL and return a pandas DataFrame."""
        return self.query(sql, params).df()

    # -------------------------------------------------------------------------
    # Convenience analytics queries
    # -------------------------------------------------------------------------

    def source_summary(self):
        """Row counts and average score per source."""
        return self.query_df("""
            SELECT source, COUNT(*) AS count, AVG(score) AS avg_score,
                   SUM(answer_count) AS total_answers
            FROM canonical
            GROUP BY source
            ORDER BY count DESC
        """)

    def top_tags(self, source: str | None = None, n: int = 50):
        """Most frequent tags across the dataset."""
        filter_clause = f"WHERE source = '{source}'" if source else ""
        return self.query_df(f"""
            SELECT tag, COUNT(*) AS freq
            FROM (
                SELECT unnest(string_split(tags, ',')) AS tag
                FROM canonical
                {filter_clause}
            )
            WHERE tag != ''
            GROUP BY tag
            ORDER BY freq DESC
            LIMIT {n}
        """)

    def score_distribution(self, source: str | None = None):
        filter_clause = f"WHERE source = '{source}'" if source else ""
        return self.query_df(f"""
            SELECT
                score_bucket,
                COUNT(*) AS count
            FROM (
                SELECT FLOOR(score / 10) * 10 AS score_bucket
                FROM canonical
                {filter_clause}
            )
            GROUP BY score_bucket
            ORDER BY score_bucket
        """)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
