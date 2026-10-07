"""
CLI: data-pipeline — run the full ETL pipeline for one or more sources.

Usage:
  data-pipeline run --source squad
  data-pipeline run --source stackexchange --limit 50000 --skip-embed
  data-pipeline run --source all --chunk-strategy hierarchical
"""
from __future__ import annotations

import logging
from pathlib import Path

import typer
import yaml

app = typer.Typer(name="data-pipeline", help="Run ETL pipeline stages.")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


@app.command("run")
def run_pipeline(
    source: str = typer.Argument(..., help="Source name or 'all'"),
    config_dir: Path = typer.Option(Path("./config"), help="Config directory"),
    data_dir: Path = typer.Option(Path("./data"), help="Data root directory"),
    limit: int = typer.Option(0, help="Limit records per source (0 = unlimited)"),
    chunk_strategy: str = typer.Option("canonical_qa", help="Chunking strategy"),
    skip_embed: bool = typer.Option(False, help="Skip embedding stage"),
    skip_graph: bool = typer.Option(False, help="Skip graph extraction stage"),
    incremental: bool = typer.Option(False, "--incremental", help="Skip rows already ingested (uses checkpoint watermark)"),
) -> None:
    from data_module.sources import SOURCE_REGISTRY
    from data_module.pipelines.orchestrator import Orchestrator, PipelineInterrupted
    from data_module.storage import build_stores
    from data_module.storage.sqlite_store import SQLiteStore

    pipeline_cfg = _load_yaml(config_dir / "pipeline.yaml")
    # pipeline.yaml has a top-level 'pipeline:' key — unwrap it if present
    if "pipeline" in pipeline_cfg and isinstance(pipeline_cfg["pipeline"], dict):
        pipeline_cfg = pipeline_cfg["pipeline"]
    if chunk_strategy:
        pipeline_cfg["default_chunk_strategy"] = chunk_strategy

    storage_cfg = _load_yaml(config_dir / "storage.yaml")
    stores = build_stores(storage_cfg, data_root=data_dir)

    db_path = data_dir / "processed" / "pipeline_state.db"
    sources_to_run = list(SOURCE_REGISTRY.keys()) if source == "all" else [source]

    for src_name in sources_to_run:
        typer.echo(f"\n=== Pipeline: {src_name} ===")
        src_cfg_file = config_dir / "sources" / f"{src_name}.yaml"
        if not src_cfg_file.exists():
            typer.echo(f"  No config for {src_name}, skipping.", err=True)
            continue
        source_cfg = _load_yaml(src_cfg_file).get(src_name, {})
        if src_name == "local_file":
            source_cfg = {
                **source_cfg,
                "_config_file_parent": str(src_cfg_file.parent.resolve()),
            }

        sqlite = SQLiteStore(db_path)
        cp = sqlite.get_checkpoint(src_name)
        sqlite.close()

        # --incremental: inject skip_rows from the stored watermark
        if incremental:
            if cp and cp.get("rows_ingested", 0) > 0:
                skip = cp["rows_ingested"]
                typer.echo(f"  [incremental] Checkpoint found: skipping first {skip} rows.")
                source_cfg = {**source_cfg, "skip_rows": skip}
            else:
                typer.echo(f"  [incremental] No checkpoint for {src_name} — running full ingest.")

        # Wikidata: auto-resume after a partial checkpoint (crash / Ctrl+C) without --incremental
        elif src_name == "wikidata" and cp and cp.get("status") == "partial" and cp.get("rows_ingested", 0) > 0:
            skip = cp["rows_ingested"]
            typer.echo(
                f"  [wikidata] Partial checkpoint found: resuming (skip_rows={skip}). "
                "Ensure graph.pkl.gz matches this checkpoint."
            )
            source_cfg = {**source_cfg, "skip_rows": skip}

        orchestrator = Orchestrator(
            pipeline_cfg=pipeline_cfg,
            raw_dir=data_dir / "raw",
            parquet_store=stores["parquet"],
            lance_store=stores["lance"],
            graph_store=stores["graph"],
            sqlite_db_path=db_path,
        )
        try:
            orchestrator.run(
                source_name=src_name,
                source_cfg=source_cfg,
                limit=limit,
                skip_embed=skip_embed,
                skip_graph=skip_graph,
            )
        except PipelineInterrupted as exc:
            typer.echo(
                (
                    f"  [{exc.source_name}] Interrupted by {exc.signal_name}. "
                    f"Saved progress at entities={exc.entities_written} "
                    f"triples={exc.triples_written}."
                ),
                err=True,
            )
            raise typer.Exit(code=130)

    # Save graph if NetworkX
    graph = stores.get("graph")
    if hasattr(graph, "save"):
        graph.save()

    typer.echo("\nAll pipelines complete.")


@app.command("status")
def show_status(
    data_dir: Path = typer.Option(Path("./data"), help="Data root directory"),
) -> None:
    """Show ingestion checkpoints and pipeline run history."""
    from data_module.storage.sqlite_store import SQLiteStore
    db_path = data_dir / "processed" / "pipeline_state.db"
    if not db_path.exists():
        typer.echo("No pipeline runs recorded yet.")
        return

    store = SQLiteStore(db_path)
    checkpoints = store.get_all_checkpoints()
    history = store.get_run_history()
    store.close()

    # ── Checkpoint table ──────────────────────────────────────────────
    typer.echo("\n── Source Checkpoints (incremental watermarks) ──")
    if not checkpoints:
        typer.echo("  No checkpoints recorded. Run the pipeline first.")
    else:
        header = f"  {'SOURCE':<22} {'ROWS':>8}  {'MAX_ROWS':>8}  {'STATUS':<10}  {'LAST RUN':<20}  VERSION"
        typer.echo(header)
        typer.echo("  " + "-" * (len(header) - 2))
        for cp in checkpoints:
            version = (cp.get("dataset_version") or "")[:20]
            typer.echo(
                f"  {cp['source_name']:<22} {cp['rows_ingested']:>8}  "
                f"{(cp['max_rows_config'] or 0):>8}  {cp['status']:<10}  "
                f"{(cp['last_ingested_at'] or '')[:19]:<20}  {version}"
            )

    # ── Recent run history ────────────────────────────────────────────
    typer.echo("\n── Recent Pipeline Runs ──")
    if not history:
        typer.echo("  No runs recorded.")
    else:
        for run in history[:20]:
            typer.echo(
                f"  [{run['run_id']:>4}] {run['source']:<22} {run['status']:<10} "
                f"in={run['records_in']:<8} out={run['records_out']:<8} "
                f"started={run['started_at']}"
            )

    # ── Quick "what's left to ingest" hint ────────────────────────────
    ingested = {cp["source_name"] for cp in checkpoints if cp["status"] == "complete"}
    all_sources = {"squad", "hotpotqa", "triviaqa", "openassistant",
                   "natural_questions", "ms_marco", "wikipedia", "stackexchange", "wikidata",
                   "local_file"}
    missing = all_sources - ingested
    if missing:
        typer.echo(f"\n── Not yet ingested: {', '.join(sorted(missing))} ──")


@app.command("backfill-checkpoints")
def backfill_checkpoints(
    data_dir: Path = typer.Option(Path("./data"), help="Data root directory"),
) -> None:
    """
    Backfill source_checkpoints from already-ingested canonical Parquet data.

    Run this once after upgrading to the checkpoint system so that sources
    ingested before checkpointing was added are properly recorded.
    """
    import pyarrow.parquet as pq
    from data_module.storage.sqlite_store import SQLiteStore

    canonical_root = data_dir / "processed" / "canonical"
    if not canonical_root.exists():
        typer.echo("No canonical data found — nothing to backfill.")
        return

    db_path = data_dir / "processed" / "pipeline_state.db"
    store = SQLiteStore(db_path)

    # Read existing checkpoints so we don't overwrite a newer one
    existing = {cp["source_name"]: cp for cp in store.get_all_checkpoints()}

    typer.echo(f"\nScanning {canonical_root} …\n")
    backfilled = 0

    for partition_dir in sorted(canonical_root.iterdir()):
        if not partition_dir.is_dir():
            continue
        # Partition dirs are named  source=<name>
        if not partition_dir.name.startswith("source="):
            continue
        source_name = partition_dir.name.removeprefix("source=")

        # Count rows across all parquet files in this partition
        parquet_files = list(partition_dir.glob("**/*.parquet"))
        if not parquet_files:
            typer.echo(f"  {source_name:<22} — no parquet files, skipping.")
            continue

        total_rows = sum(
            pq.read_metadata(str(f)).num_rows for f in parquet_files
        )

        if total_rows == 0:
            typer.echo(f"  {source_name:<22} — 0 rows (likely failed run), skipping.")
            continue

        if source_name in existing:
            typer.echo(
                f"  {source_name:<22} — checkpoint already exists "
                f"({existing[source_name]['rows_ingested']} rows), skipping."
            )
            continue

        # Look up last successful run timestamp from pipeline_runs
        last_run = store._conn.execute(
            "SELECT finished_at FROM pipeline_runs "
            "WHERE source=? AND status='done' ORDER BY run_id DESC LIMIT 1",
            (source_name,),
        ).fetchone()
        ingested_at = last_run["finished_at"] if last_run else None

        store.write_checkpoint(
            source_name=source_name,
            rows_ingested=total_rows,
            dataset_version=None,   # not tracked for pre-checkpoint runs
            max_rows_config=None,
            status="complete",
        )
        # Patch the timestamp if we found it in pipeline_runs
        if ingested_at:
            store._conn.execute(
                "UPDATE source_checkpoints SET last_ingested_at=? WHERE source_name=?",
                (ingested_at, source_name),
            )
            store._conn.commit()

        typer.echo(f"  {source_name:<22} — backfilled  {total_rows:>8} rows")
        backfilled += 1

    store.close()
    typer.echo(f"\nDone. Backfilled {backfilled} source(s).")
    typer.echo("Run  `data-pipeline status`  to verify.")


if __name__ == "__main__":
    app()
