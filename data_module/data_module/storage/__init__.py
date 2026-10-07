"""data_module.storage — storage backend registry and factory."""
from pathlib import Path

from .base import AbstractStore
from .parquet_store import ParquetStore
from .duckdb_store import DuckDBStore
from .lance_store import LanceStore
from .sqlite_store import SQLiteStore
from .graph_store import NetworkXGraphStore, Neo4jGraphStore, get_graph_store


def build_stores(storage_cfg: dict, data_root: Path | None = None):
    """
    Construct all storage backends from a storage config dict.

    Returns a dict with keys: parquet, duckdb, lance, sqlite, graph.
    """
    # storage.yaml has a top-level 'storage:' key — unwrap it if present
    if "storage" in storage_cfg and isinstance(storage_cfg["storage"], dict):
        storage_cfg = storage_cfg["storage"]

    if data_root is None:
        data_root = Path(storage_cfg.get("data_root", "./data"))

    def resolve(path_str: str) -> Path:
        p = Path(path_str.replace("${data_root}", str(data_root)))
        return p

    parquet_cfg = storage_cfg.get("parquet", {})
    parquet = ParquetStore(
        canonical_dir=resolve(parquet_cfg.get("canonical_dir", "${data_root}/processed/canonical")),
        chunks_dir=resolve(parquet_cfg.get("chunks_dir", "${data_root}/processed/chunks")),
        compression=parquet_cfg.get("compression", "zstd"),
    )

    duckdb_cfg = storage_cfg.get("duckdb", {})
    duckdb_store = DuckDBStore(
        db_path=resolve(duckdb_cfg.get("db_path", "${data_root}/processed/analytics.duckdb")),
        canonical_dir=resolve(parquet_cfg.get("canonical_dir", "${data_root}/processed/canonical")),
        chunks_dir=resolve(parquet_cfg.get("chunks_dir", "${data_root}/processed/chunks")),
        memory_limit=duckdb_cfg.get("memory_limit", "4GB"),
        threads=duckdb_cfg.get("threads", 4),
    )

    lance_cfg = storage_cfg.get("lance", {})
    lance = LanceStore(
        db_path=resolve(lance_cfg.get("db_path", "${data_root}/index/vectors")),
        table_name=lance_cfg.get("table_name", "chunks"),
        metric=lance_cfg.get("metric", "cosine"),
    )

    sqlite_cfg = storage_cfg.get("sqlite", {})
    sqlite = SQLiteStore(
        db_path=resolve(sqlite_cfg.get("db_path", "${data_root}/processed/pipeline_state.db")),
    )

    graph_cfg = storage_cfg.get("graph", {})
    graph_cfg_resolved = dict(graph_cfg)
    if "networkx_path" in graph_cfg_resolved:
        graph_cfg_resolved["networkx_path"] = str(
            resolve(graph_cfg_resolved["networkx_path"])
        )
    graph = get_graph_store(graph_cfg_resolved)

    return {
        "parquet": parquet,
        "duckdb": duckdb_store,
        "lance": lance,
        "sqlite": sqlite,
        "graph": graph,
    }


__all__ = [
    "AbstractStore",
    "ParquetStore",
    "DuckDBStore",
    "LanceStore",
    "SQLiteStore",
    "NetworkXGraphStore",
    "Neo4jGraphStore",
    "get_graph_store",
    "build_stores",
]
