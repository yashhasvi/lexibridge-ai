"""
CLI: data-download — download raw source files.

Usage:
  data-download stackexchange --sites stackoverflow unix --limit 0
  data-download squad
  data-download all
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import typer
import yaml

app = typer.Typer(name="data-download", help="Download raw source data files.")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _load_config(config_dir: Path, source_name: str) -> dict:
    cfg_file = config_dir / "sources" / f"{source_name}.yaml"
    if not cfg_file.exists():
        typer.echo(f"No config found for source '{source_name}' at {cfg_file}", err=True)
        raise typer.Exit(1)
    with open(cfg_file) as f:
        cfg = yaml.safe_load(f).get(source_name, {})
    if source_name == "local_file":
        cfg = {**cfg, "_config_file_parent": str(cfg_file.parent.resolve())}
    return cfg


@app.command()
def main(
    source: str = typer.Argument(..., help="Source name, e.g. 'stackexchange', or 'all'"),
    config_dir: Path = typer.Option(Path("./config"), help="Path to config/ directory"),
    data_dir: Path = typer.Option(Path("./data/raw"), help="Path to raw data directory"),
    sites: list[str] | None = typer.Option(None, help="For stackexchange: comma-separated site list"),
    limit: int = typer.Option(0, help="Limit records (0 = unlimited, for testing)"),
    skip_if_exists: bool = typer.Option(True, help="Skip download if raw files already present"),
) -> None:
    from data_module.sources import SOURCE_REGISTRY

    sources_to_run = list(SOURCE_REGISTRY.keys()) if source == "all" else [source]

    for src_name in sources_to_run:
        typer.echo(f"\n=== Downloading: {src_name} ===")
        try:
            source_cfg = _load_config(config_dir, src_name)
        except SystemExit:
            continue

        # Allow CLI override of sites for stackexchange
        if sites and src_name == "stackexchange":
            source_cfg["sites"] = sites

        cls = SOURCE_REGISTRY.get(src_name)
        if cls is None:
            typer.echo(f"Unknown source: {src_name}", err=True)
            continue

        raw_dir = data_dir / src_name
        instance = cls(raw_dir, source_cfg)

        if skip_if_exists and instance.downloader.is_downloaded():
            typer.echo(f"  Already downloaded. Use --no-skip-if-exists to re-download.")
            continue

        downloaded = instance.downloader.download()
        typer.echo(f"  Downloaded {len(downloaded)} file(s).")

    typer.echo("\nAll downloads complete.")


if __name__ == "__main__":
    app()
