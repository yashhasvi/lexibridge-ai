"""
Shared Hugging Face downloader — used by SQuAD, NQ, MS MARCO, HotpotQA, TriviaQA, OASST2.

Uses the `datasets` library to download and cache to raw_dir.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Generator

from .base import AbstractDownloader, AbstractParser

logger = logging.getLogger(__name__)


class HFDownloader(AbstractDownloader):
    """Downloads a Hugging Face dataset to local cache."""

    def __init__(self, raw_dir: Path, config: dict) -> None:
        super().__init__(raw_dir, config)
        self.hf_id: str = config["huggingface_id"]
        self.hf_config: str | None = config.get("config")
        self.splits: list[str] = config.get("splits", ["train"])
        # Set after download() completes — readable by orchestrator for checkpointing
        self.dataset_version: str | None = None

    def download(self) -> list[Path]:
        from datasets import load_dataset

        max_rows: int = self.config.get("max_rows", 0)
        skip_rows: int = self.config.get("skip_rows", 0)
        streaming: bool = self.config.get("streaming", False)

        logger.info(
            "[HF] Downloading %s (config=%s, streaming=%s, skip=%d)…",
            self.hf_id, self.hf_config, streaming, skip_rows,
        )
        kwargs: dict = {}
        if self.hf_config:
            kwargs["name"] = self.hf_config

        if streaming:
            return self._download_streaming(kwargs, max_rows, skip_rows)

        # Non-streaming: cache entire dataset locally then truncate/skip.
        kwargs["cache_dir"] = str(self.raw_dir)
        ds = load_dataset(self.hf_id, **kwargs)

        # Capture dataset version (HF commit hash) for checkpoint tracking
        try:
            cache_files = getattr(ds, "cache_files", {})
            first_split_files = next(iter(cache_files.values()), [])
            if first_split_files:
                # Parent dir of the cache file is the dataset revision hash
                self.dataset_version = Path(first_split_files[0]["filename"]).parent.name
        except Exception:
            self.dataset_version = None

        saved: list[Path] = []
        for split in self.splits:
            if split not in ds:
                logger.warning("[HF] Split '%s' not found in %s", split, self.hf_id)
                continue
            split_ds = ds[split]
            # Skip already-ingested rows for incremental runs
            if skip_rows and skip_rows < len(split_ds):
                logger.info("[HF] Incremental: skipping first %d rows of %s", skip_rows, split)
                split_ds = split_ds.select(range(skip_rows, len(split_ds)))
            if max_rows and len(split_ds) > max_rows:
                logger.info(
                    "[HF] Truncating %s split from %d → %d rows (max_rows limit)",
                    split, len(split_ds), max_rows,
                )
                split_ds = split_ds.select(range(max_rows))
            out_path = self.raw_dir / f"{split}.parquet"
            split_ds.to_parquet(str(out_path))
            logger.info("[HF] Saved %s → %s (%d rows)", split, out_path.name, len(split_ds))
            saved.append(out_path)

        return saved

    def _download_streaming(self, extra_kwargs: dict, max_rows: int, skip_rows: int = 0) -> list[Path]:
        """
        Stream rows from HF without caching the full dataset to disk.
        Writes directly to Parquet in batches — safe for huge datasets like
        Wikipedia (~20 GB Arrow cache) where we only need a fraction of rows.
        """
        import pyarrow as pa
        import pyarrow.parquet as pq
        from datasets import load_dataset

        ds = load_dataset(self.hf_id, streaming=True, **extra_kwargs)
        saved: list[Path] = []
        WRITE_BATCH = 1000  # rows per Parquet row-group

        for split in self.splits:
            if split not in ds:
                logger.warning("[HF] Streaming split '%s' not found, skipping.", split)
                continue

            out_path = self.raw_dir / f"{split}.parquet"
            self.raw_dir.mkdir(parents=True, exist_ok=True)

            writer: pq.ParquetWriter | None = None
            total = 0
            batch: list[dict] = []

            def _flush(batch: list[dict], writer_ref: list) -> pq.ParquetWriter:
                table = pa.Table.from_pylist(batch)
                if writer_ref[0] is None:
                    writer_ref[0] = pq.ParquetWriter(str(out_path), table.schema)
                writer_ref[0].write_table(table)
                return writer_ref[0]

            writer_ref: list = [None]
            for row in ds[split]:
                # Skip already-ingested rows for incremental streaming runs
                if skip_rows and total < skip_rows:
                    total += 1
                    continue
                batch.append(row)
                total += 1
                if len(batch) >= WRITE_BATCH:
                    _flush(batch, writer_ref)
                    batch.clear()
                    if total % 10000 == 0:
                        logger.info("[HF] Streamed %d rows from %s/%s…", total, self.hf_id, split)
                if max_rows and total >= max_rows:
                    break

            if batch:
                _flush(batch, writer_ref)

            if writer_ref[0] is not None:
                writer_ref[0].close()

            logger.info("[HF] Streamed %s → %s (%d rows)", split, out_path.name, total)
            saved.append(out_path)

        return saved

    def is_downloaded(self) -> bool:
        parquet_files = list(self.raw_dir.glob("*.parquet"))
        return len(parquet_files) >= len(self.splits)


class HFParser(AbstractParser):
    """Reads cached Parquet files and yields rows as dicts."""

    def __init__(self, raw_dir: Path, config: dict) -> None:
        super().__init__(raw_dir, config)
        self.splits: list[str] = config.get("splits", ["train"])
        # Optional: only read these columns (saves memory for large datasets
        # with heavy unused columns, e.g. NQ's document.html)
        self.read_columns: list[str] | None = config.get("read_columns") or None

    def parse(self) -> Generator[dict, None, None]:
        import pandas as pd

        for split in self.splits:
            parquet_path = self.raw_dir / f"{split}.parquet"
            if not parquet_path.exists():
                logger.warning("[HF] %s not found, skipping.", parquet_path)
                continue
            logger.info("[HF] Reading %s…", parquet_path.name)
            df = pd.read_parquet(parquet_path, columns=self.read_columns)
            for row in df.to_dict(orient="records"):
                row["_split"] = split
                yield row
