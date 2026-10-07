"""
Pipeline orchestrator — runs the full ETL pipeline for a given source.

Stages (in order):
  1. Ingest:    source.iter_canonical() → CanonicalQA stream
  2. Validate:  dedup by content_hash
  3. Normalize: HTML strip, text clean
  4. Enrich:    NER entity mentions
  5a. Store canonical:  write CanonicalQA to Parquet
  5b. Chunk:    CanonicalQA → ChunkRecords
  5c. Embed:    ChunkRecord → ChunkRecord with embeddings
  5d. Store chunks: write ChunkRecords to Parquet + LanceDB
  5e. Graph:    CanonicalQA → Triples → GraphStore
"""
from __future__ import annotations

import logging
import signal
from pathlib import Path
from typing import TYPE_CHECKING

from .ingest import IngestValidator, load_source
from .transform import Enricher, Normalizer
from .chunk import Chunker, Strategy
from .embed import BatchEmbedder
from .graph import GraphBuilder

if TYPE_CHECKING:
    from ..storage.parquet_store import ParquetStore
    from ..storage.lance_store import LanceStore
    from ..storage.graph_store import GraphStore

logger = logging.getLogger(__name__)


class PipelineInterrupted(Exception):
    """Raised after persisting partial progress for an interrupted run."""

    def __init__(
        self,
        source_name: str,
        signal_name: str,
        entities_written: int,
        triples_written: int,
    ) -> None:
        super().__init__(f"{source_name} interrupted by {signal_name}")
        self.source_name = source_name
        self.signal_name = signal_name
        self.entities_written = entities_written
        self.triples_written = triples_written


class PipelineConfig:
    def __init__(self, cfg: dict) -> None:
        self.chunk_strategy = Strategy(cfg.get("default_chunk_strategy", "canonical_qa"))
        self.max_chunk_tokens = cfg.get("max_chunk_tokens", 512)
        self.embedding_model = cfg.get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
        self.embedding_batch_size = cfg.get("embedding_batch_size", 256)
        self.embedding_device = cfg.get("embedding_device", "cpu")
        self.spacy_model = cfg.get("spacy_model", "en_core_web_sm")
        self.spacy_batch_size = cfg.get("spacy_batch_size", 64)
        self.spacy_n_process = cfg.get("spacy_n_process", 1)
        self.run_ner = cfg.get("run_ner", True)
        self.run_entity_linking = cfg.get("run_entity_linking", False)
        self.strip_html = cfg.get("strip_html", True)
        self.normalize_whitespace = cfg.get("normalize_whitespace", True)
        self.min_text_length = cfg.get("min_text_length", 20)
        self.dedup_exact = cfg.get("dedup_exact", True)
        self.batch_size = cfg.get("batch_size", 1000)
        # NetworkX: write graph.pkl.gz + SQLite partial checkpoint every N triple-batch flushes (0 = only at end).
        self.wikidata_save_every_batches = int(cfg.get("wikidata_save_every_batches", 5))


class Orchestrator:
    """
    Wires all pipeline stages together.

    Example usage:
        orchestrator = Orchestrator(pipeline_cfg, storage_cfg, raw_dir)
        orchestrator.run(source_name="squad", source_cfg={...}, limit=0)
    """

    def __init__(
        self,
        pipeline_cfg: dict,
        raw_dir: Path,
        parquet_store: "ParquetStore",
        lance_store: "LanceStore",
        graph_store: "GraphStore",
        sqlite_db_path: Path,
    ) -> None:
        self.cfg = PipelineConfig(pipeline_cfg)
        self.raw_dir = raw_dir
        self.parquet_store = parquet_store
        self.lance_store = lance_store
        self.graph_store = graph_store
        self.sqlite_db_path = sqlite_db_path

    def run(
        self,
        source_name: str,
        source_cfg: dict,
        limit: int = 0,
        skip_embed: bool = False,
        skip_graph: bool = False,
    ) -> None:
        logger.info("=== Pipeline start: %s ===", source_name)

        if source_name == "wikidata":
            entities_written, triples_written = self._run_wikidata(
                source_cfg=source_cfg,
                limit=limit,
                skip_graph=skip_graph,
            )
            logger.info(
                "=== Pipeline complete: %s (entities=%d, triples=%d) ===",
                source_name,
                entities_written,
                triples_written,
            )
            self._write_checkpoint(
                source_name, source_cfg, rows_written=entities_written, status="complete"
            )
            return

        # Stage 1: Ingest
        raw_stream = load_source(source_name, self.raw_dir, source_cfg, limit)

        # Stage 2: Validate + dedup
        with IngestValidator(
            db_path=self.sqlite_db_path,
            dedup_exact=self.cfg.dedup_exact,
            min_text_length=self.cfg.min_text_length,
        ) as validator:

            validated = validator.validate_and_dedup(raw_stream)

            # Stage 3: Normalize
            normalizer = Normalizer(
                strip_html=self.cfg.strip_html,
                normalize_whitespace=self.cfg.normalize_whitespace,
                min_text_length=self.cfg.min_text_length,
            )
            normalized = normalizer.normalize_stream(validated)

            # Stage 4: Enrich (NER)
            enricher = Enricher(
                spacy_model=self.cfg.spacy_model,
                run_ner=self.cfg.run_ner,
                run_entity_linking=self.cfg.run_entity_linking,
            )
            enriched = enricher.enrich_stream(
                normalized,
                batch_size=self.cfg.spacy_batch_size,
                n_process=self.cfg.spacy_n_process,
            )

            # Stage 5a: Store canonical Parquet + fork streams
            logger.info("Starting ingest → normalize → enrich (NER) pipeline…")
            canonical_records = list(enriched)   # materialize so we can iterate twice
            logger.info("Enrichment complete. Storing %d canonical records to Parquet…", len(canonical_records))
            self.parquet_store.write_canonical(iter(canonical_records), source_name)

            # Stage 5b-d: Chunk → Embed → Store
            chunker = Chunker(strategy=self.cfg.chunk_strategy, max_tokens=self.cfg.max_chunk_tokens)
            chunk_stream = chunker.chunk_stream(iter(canonical_records))

            if not skip_embed:
                embedder = BatchEmbedder(
                    model_name=self.cfg.embedding_model,
                    batch_size=self.cfg.embedding_batch_size,
                    device=self.cfg.embedding_device,
                )
                chunk_stream = embedder.embed_stream(chunk_stream)

            chunk_list = list(chunk_stream)
            logger.info("Storing %d chunks to Parquet + LanceDB…", len(chunk_list))
            self.parquet_store.write_chunks(iter(chunk_list), source_name)
            self.lance_store.upsert_chunks(chunk_list)

            # Stage 5e: Graph
            if not skip_graph:
                graph_builder = GraphBuilder(self.graph_store, batch_size=self.cfg.batch_size)
                graph_builder.build(iter(canonical_records))

        logger.info("=== Pipeline complete: %s ===", source_name)

        # Record watermark for incremental ingestion on future runs
        self._write_checkpoint(source_name, source_cfg, len(canonical_records))

    def _run_wikidata(
        self,
        source_cfg: dict,
        limit: int = 0,
        skip_graph: bool = False,
    ) -> tuple[int, int]:
        """
        Special pipeline path for Wikidata.

        Wikidata is graph-first data (Entity + Triple stream), not CanonicalQA.
        """
        from ..sources.wikidata import WikidataSource

        source = WikidataSource(self.raw_dir / "wikidata", source_cfg)
        if not source.downloader.is_downloaded():
            logger.info("[wikidata] Downloading dump before ingestion…")
            source.downloader.download()

        if skip_graph:
            logger.info("[wikidata] skip_graph=true -> downloaded/verified raw dump only.")
            return (0, 0)

        skip_n = int(source_cfg.get("skip_rows", 0))
        if skip_n:
            logger.info("[wikidata] Resuming: skip_rows=%d (already on disk / prior partial run).", skip_n)

        entities_written = skip_n
        triples_written = 0
        entity_batch = []
        triple_batch = []
        batch_size = max(1000, int(self.cfg.batch_size))
        save_every = max(0, int(self.cfg.wikidata_save_every_batches))
        flush_count = 0
        stop_signal: int | None = None
        prev_sigint = signal.getsignal(signal.SIGINT)
        prev_sigterm = signal.getsignal(signal.SIGTERM)

        def _handle_stop(signum: int, _frame) -> None:
            nonlocal stop_signal
            if stop_signal is None:
                stop_signal = signum
                logger.warning(
                    "[wikidata] Received %s; saving progress after the current batch.",
                    signal.Signals(signum).name,
                )
            else:
                logger.warning(
                    "[wikidata] Received %s again; still waiting for the current batch to finish.",
                    signal.Signals(signum).name,
                )

        signal.signal(signal.SIGINT, _handle_stop)
        signal.signal(signal.SIGTERM, _handle_stop)
        try:
            for entity, triples in source.iter_entities_triples(limit=limit):
                if stop_signal is not None:
                    break

                entity_batch.append(entity)
                triple_batch.extend(triples)

                if len(triple_batch) >= batch_size:
                    self.graph_store.upsert_entities(entity_batch)
                    self.graph_store.upsert_triples(triple_batch)
                    entities_written += len(entity_batch)
                    triples_written += len(triple_batch)
                    logger.info(
                        "[wikidata] upserted entities=%d triples=%d",
                        entities_written,
                        triples_written,
                    )
                    entity_batch = []
                    triple_batch = []
                    flush_count += 1
                    if save_every and flush_count % save_every == 0:
                        self._wikidata_persist_progress(source_cfg, entities_written)

            if triple_batch:
                self.graph_store.upsert_entities(entity_batch)
                self.graph_store.upsert_triples(triple_batch)
                entities_written += len(entity_batch)
                triples_written += len(triple_batch)
                flush_count += 1

            # Persist any trailing flushes that did not land on save_every (also idempotent after a modulo save).
            if stop_signal is not None or (save_every and flush_count > 0):
                self._wikidata_persist_progress(source_cfg, entities_written)
            elif hasattr(self.graph_store, "save"):
                self.graph_store.save()
        finally:
            signal.signal(signal.SIGINT, prev_sigint)
            signal.signal(signal.SIGTERM, prev_sigterm)

        if stop_signal is not None:
            signal_name = signal.Signals(stop_signal).name
            raise PipelineInterrupted(
                source_name="wikidata",
                signal_name=signal_name,
                entities_written=entities_written,
                triples_written=triples_written,
            )

        logger.info(
            "[wikidata] graph ingestion complete: entities=%d triples=%d",
            entities_written,
            triples_written,
        )
        return (entities_written, triples_written)

    def _wikidata_persist_progress(self, source_cfg: dict, entities_written: int) -> None:
        """Flush graph to disk (NetworkX) and record partial watermark for resume."""
        logger.info("[wikidata] checkpoint: saving graph + partial watermark (entities=%d).", entities_written)
        if hasattr(self.graph_store, "save"):
            self.graph_store.save()
        self._write_checkpoint(
            "wikidata", source_cfg, rows_written=entities_written, status="partial"
        )

    def _write_checkpoint(
        self,
        source_name: str,
        source_cfg: dict,
        rows_written: int,
        status: str = "complete",
    ) -> None:
        """Persist a watermark so future --incremental runs know where to start."""
        from ..storage.sqlite_store import SQLiteStore
        from ..sources import SOURCE_REGISTRY
        try:
            # Try to read dataset_version from the HFDownloader if applicable
            dataset_version: str | None = source_cfg.get("_dataset_version")
            cls = SOURCE_REGISTRY.get(source_name)
            if dataset_version is None and cls is not None:
                try:
                    src = cls(self.raw_dir / source_name, source_cfg)
                    if hasattr(src.downloader, "dataset_version"):
                        dataset_version = src.downloader.dataset_version
                except Exception:
                    pass

            store = SQLiteStore(self.sqlite_db_path)
            store.write_checkpoint(
                source_name=source_name,
                rows_ingested=rows_written,
                dataset_version=dataset_version,
                max_rows_config=source_cfg.get("max_rows"),
                status=status,
            )
            store.close()
            logger.info(
                "[checkpoint] Recorded watermark for %s: %d rows ingested (%s).",
                source_name,
                rows_written,
                status,
            )
        except Exception as exc:
            logger.warning("[checkpoint] Failed to write checkpoint for %s: %s", source_name, exc)
