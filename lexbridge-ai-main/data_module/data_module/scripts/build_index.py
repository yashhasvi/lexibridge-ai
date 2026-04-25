"""
CLI: data-index — build or rebuild vector and graph indexes.

Usage:
  data-index build --source all
  data-index build --source stackexchange --skip-graph
  data-index rebuild-graph --source squad
  data-index stats
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import typer
import yaml

app = typer.Typer(name="data-index", help="Build and manage vector and graph indexes.")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _parquet_table_to_canonicals(table):
    """Reconstruct CanonicalQA objects from a PyArrow canonical table."""
    from datetime import datetime
    from data_module.schema.canonical import CanonicalAnswer, CanonicalQA
    from data_module.schema.provenance import License, SourceName

    records = []
    for row in table.to_pylist():
        try:
            answers_raw = json.loads(row.get("answers_json") or "[]")
            answers = [CanonicalAnswer(**a) for a in answers_raw]
            records.append(CanonicalQA(
                id=row["id"],
                source=SourceName(row["source"]),
                source_id=row["source_id"],
                site=row.get("site") or None,
                title=row["title"],
                body=row["body"],
                body_html=None,
                answers=answers,
                accepted_answer_id=row.get("accepted_answer_id") or None,
                tags=json.loads(row.get("tags") or "[]"),
                language=row.get("language", "en"),
                score=row.get("score", 0),
                view_count=row.get("view_count") or None,
                answer_count=row.get("answer_count", 0),
                created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
                source_url=row.get("source_url") or None,
                license=License(row.get("license", "unknown")),
                content_hash=row.get("content_hash", ""),
            ))
        except Exception as exc:
            logging.warning("Skipping malformed row %s: %s", row.get("id"), exc)
    return records


@app.command("build")
def build_index(
    source: str = typer.Option(
        "all",
        "--source",
        "-s",
        help="Source name or 'all' (vector index covers all chunks in LanceDB)",
    ),
    config_dir: Path = typer.Option(Path("./config"), help="Config directory"),
    data_dir: Path = typer.Option(Path("./data"), help="Data root directory"),
    skip_vector: bool = typer.Option(False, help="Skip LanceDB ANN index creation"),
    skip_graph: bool = typer.Option(False, help="Skip graph index"),
    num_partitions: int = typer.Option(256, help="LanceDB IVF partitions"),
    num_sub_vectors: int = typer.Option(96, help="LanceDB PQ sub-vectors"),
) -> None:
    """
    Build ANN index on LanceDB and optionally rebuild graph from Parquet.
    Run this after bulk-loading data with `data-pipeline run`.
    """
    from data_module.storage import build_stores

    storage_cfg = _load_yaml(config_dir / "storage.yaml")
    stores = build_stores(storage_cfg, data_root=data_dir)

    lance = stores["lance"]
    graph = stores["graph"]

    if not skip_vector:
        typer.echo(f"Building ANN index on LanceDB ({lance.count()} vectors)…")
        try:
            lance.create_index(
                num_partitions=num_partitions,
                num_sub_vectors=num_sub_vectors,
            )
            typer.echo("  ANN index created.")
        except Exception as exc:
            typer.echo(f"  ANN index creation failed: {exc}", err=True)

    if not skip_graph and hasattr(graph, "save"):
        typer.echo("Saving graph store…")
        graph.save()
        typer.echo("  Graph saved.")

    typer.echo("Index build complete.")


@app.command("rebuild-graph")
def rebuild_graph(
    source: str = typer.Option("all", "--source", "-s", help="Source name or 'all'"),
    config_dir: Path = typer.Option(Path("./config"), help="Config directory"),
    data_dir: Path = typer.Option(Path("./data"), help="Data root directory"),
) -> None:
    """
    Rebuild the graph index by reading directly from canonical Parquet.
    Use this when the graph stage failed without needing to re-run the full pipeline.
    """
    from data_module.storage import build_stores
    from data_module.pipelines.graph.builder import GraphBuilder

    storage_cfg = _load_yaml(config_dir / "storage.yaml")
    if "storage" in storage_cfg and isinstance(storage_cfg["storage"], dict):
        storage_cfg = storage_cfg["storage"]
    stores = build_stores(storage_cfg, data_root=data_dir)

    parquet = stores["parquet"]
    graph = stores["graph"]

    src_filter = None if source == "all" else source
    typer.echo(f"Reading canonical Parquet (source={src_filter or 'all'})…")
    table = parquet.read_canonical(source=src_filter)
    typer.echo(f"  {len(table)} rows loaded.")

    records = _parquet_table_to_canonicals(table)
    typer.echo(f"  {len(records)} CanonicalQA records reconstructed.")

    builder = GraphBuilder(graph, batch_size=1000)
    builder.build(iter(records))

    if hasattr(graph, "save"):
        graph.save()
        typer.echo("Graph saved.")

    typer.echo("Graph rebuild complete.")


@app.command("stats")
def show_stats(
    config_dir: Path = typer.Option(Path("./config"), help="Config directory"),
    data_dir: Path = typer.Option(Path("./data"), help="Data root directory"),
) -> None:
    """Show index and store statistics."""
    from data_module.storage import build_stores

    storage_cfg = _load_yaml(config_dir / "storage.yaml")
    stores = build_stores(storage_cfg, data_root=data_dir)

    lance = stores["lance"]
    typer.echo(f"LanceDB chunks: {lance.count()}")

    duckdb = stores["duckdb"]
    try:
        summary = duckdb.source_summary()
        typer.echo("\nCanonical records by source:")
        typer.echo(summary.to_string())
    except Exception:
        typer.echo("  (No canonical records yet)")

    graph = stores["graph"]
    if hasattr(graph, "_g"):
        g = graph._g
        typer.echo(f"\nGraph: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")


if __name__ == "__main__":
    app()
