from __future__ import annotations

import gzip
import json
import pickle
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yaml


@dataclass
class Paths:
    repo_root: Path
    data_module_root: Path
    storage_config_path: Path
    canonical_dir: Path
    chunks_dir: Path
    duckdb_path: Path
    sqlite_path: Path
    lance_path: Path
    lance_table: str
    graph_backend: str
    networkx_graph_path: Path
    trace_dir: Path


def _resolve_template(value: str, variables: dict[str, str]) -> str:
    resolved = value
    for key, val in variables.items():
        resolved = resolved.replace(f"${{{key}}}", val)
    return resolved


def load_paths() -> Paths:
    repo_root = Path(__file__).resolve().parents[1]
    data_module_root = repo_root / "data_module"
    storage_config_path = data_module_root / "config" / "storage.yaml"

    if not storage_config_path.exists():
        raise FileNotFoundError(f"Missing config file: {storage_config_path}")

    cfg = yaml.safe_load(storage_config_path.read_text())
    storage = cfg.get("storage", {})
    data_root_rel = storage.get("data_root", "./data")

    # In this project, data paths are relative to `data_module/`.
    data_root_abs = (data_module_root / data_root_rel).resolve()
    vars_map = {"data_root": str(data_root_abs)}

    parquet_cfg = storage.get("parquet", {})
    duckdb_cfg = storage.get("duckdb", {})
    sqlite_cfg = storage.get("sqlite", {})
    lance_cfg = storage.get("lance", {})
    graph_cfg = storage.get("graph", {})

    canonical_dir = Path(_resolve_template(parquet_cfg.get("canonical_dir", "${data_root}/processed/canonical"), vars_map))
    chunks_dir = Path(_resolve_template(parquet_cfg.get("chunks_dir", "${data_root}/processed/chunks"), vars_map))
    duckdb_path = Path(_resolve_template(duckdb_cfg.get("db_path", "${data_root}/processed/analytics.duckdb"), vars_map))
    sqlite_path = Path(_resolve_template(sqlite_cfg.get("db_path", "${data_root}/processed/pipeline_state.db"), vars_map))
    lance_path = Path(_resolve_template(lance_cfg.get("db_path", "${data_root}/index/vectors"), vars_map))
    networkx_graph_path = Path(
        _resolve_template(graph_cfg.get("networkx_path", "${data_root}/index/graph/graph.pkl.gz"), vars_map)
    )

    import os
    trace_dir = Path(os.getenv("AGENTIC_TRACE_DIR", "/tmp/brain_module_traces"))

    return Paths(
        repo_root=repo_root,
        data_module_root=data_module_root,
        storage_config_path=storage_config_path,
        canonical_dir=canonical_dir,
        chunks_dir=chunks_dir,
        duckdb_path=duckdb_path,
        sqlite_path=sqlite_path,
        lance_path=lance_path,
        lance_table=lance_cfg.get("table_name", "chunks"),
        graph_backend=graph_cfg.get("backend", "networkx"),
        networkx_graph_path=networkx_graph_path,
        trace_dir=trace_dir,
    )


@st.cache_resource(show_spinner=False)
def get_duckdb_conn(paths: Paths) -> duckdb.DuckDBPyConnection:
    if paths.duckdb_path.exists():
        conn = duckdb.connect(str(paths.duckdb_path), read_only=False)
    else:
        conn = duckdb.connect(":memory:")

    for table_name, table_dir in [("canonical", paths.canonical_dir), ("chunks", paths.chunks_dir)]:
        pattern = str(table_dir / "**/*.parquet")
        try:
            conn.execute(
                f"CREATE OR REPLACE VIEW {table_name} AS "
                f"SELECT * FROM read_parquet('{pattern}', hive_partitioning=true)"
            )
        except Exception:
            # Keep app usable even when a view cannot be registered.
            pass
    return conn


def _safe_duckdb_df(conn: duckdb.DuckDBPyConnection, query: str) -> pd.DataFrame:
    try:
        return conn.execute(query).df()
    except Exception:
        return pd.DataFrame()


def _table_columns(conn: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    df = _safe_duckdb_df(conn, f"SELECT * FROM {table} LIMIT 0")
    return list(df.columns)


def _count_sqlite_table_rows(sqlite_path: Path, table_name: str) -> int | None:
    if not sqlite_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(sqlite_path))
        val = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        conn.close()
        return int(val)
    except Exception:
        return None


def _load_networkx_graph(graph_path: Path):
    if not graph_path.exists():
        return None
    try:
        with gzip.open(graph_path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def _open_lancedb(paths: Paths):
    if not paths.lance_path.exists():
        return None, None
    try:
        import lancedb

        db = lancedb.connect(str(paths.lance_path))
        table_names = _lance_table_names(db)
        if paths.lance_table not in table_names:
            return db, None
        return db, db.open_table(paths.lance_table)
    except Exception:
        return None, None


def _format_number(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return f"{value:,}"


def _sql_quote(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _lance_table_names(db: Any) -> list[str]:
    """Handle LanceDB API drift across versions."""
    try:
        raw_names: list[Any] = []
        if hasattr(db, "list_tables"):
            raw_names = list(db.list_tables())
        elif hasattr(db, "table_names"):
            raw_names = list(db.table_names())
        else:
            return []

        normalized: list[str] = []
        for item in raw_names:
            if isinstance(item, str):
                normalized.append(item)
            elif isinstance(item, (tuple, list)) and item:
                normalized.append(str(item[0]))
            else:
                normalized.append(str(item))
        return normalized
    except Exception:
        return []


def _plot(fig: Any) -> None:
    st.plotly_chart(fig, width="stretch")


def _table(df: pd.DataFrame) -> None:
    st.dataframe(df, width="stretch")


def _inject_custom_styles() -> None:
    st.markdown(
        """
        <style>
          .block-container {
            padding-top: 1.35rem;
            padding-bottom: 2rem;
          }
          .obs-hero {
            padding: 14px 16px;
            border-radius: 14px;
            border: 1px solid rgba(100, 116, 139, 0.25);
            background: linear-gradient(135deg, rgba(37, 99, 235, 0.16), rgba(14, 165, 233, 0.08));
            margin-bottom: 12px;
          }
          .obs-hero h3 {
            margin: 0 0 4px 0;
            font-size: 1.05rem;
          }
          .obs-hero p {
            margin: 0;
            opacity: 0.9;
            font-size: 0.92rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _graph_file_size_mb(graph_path: Path) -> float | None:
    if not graph_path.exists():
        return None
    try:
        return graph_path.stat().st_size / (1024 * 1024)
    except Exception:
        return None


def _coalesce_cols(columns: list[str], *candidates: str) -> str | None:
    for c in candidates:
        if c in columns:
            return c
    return None


def _with_filter(base_query: str, where_clause: str) -> str:
    if "{where}" in base_query:
        return base_query.replace("{where}", where_clause)
    return base_query


def main() -> None:
    st.set_page_config(
        page_title="MultiRAG Data Observatory",
        page_icon=":bar_chart:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _inject_custom_styles()
    st.markdown(
        """
        <div class="obs-hero">
          <h3>MultiRAG Data Observatory (v1)</h3>
          <p>Unified visibility across Parquet, DuckDB, LanceDB, SQLite, and Graph storage.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    paths = load_paths()
    conn = get_duckdb_conn(paths)

    canonical_columns = _table_columns(conn, "canonical")
    chunks_columns = _table_columns(conn, "chunks")

    with st.sidebar:
        st.header("Global Filters")
        st.caption("Applied where equivalent columns exist")

        source_values = []
        language_values = []
        year_values = []

        if "source" in canonical_columns:
            source_values = _safe_duckdb_df(
                conn, "SELECT DISTINCT source FROM canonical WHERE source IS NOT NULL ORDER BY source"
            )["source"].dropna().tolist()
        if "language" in canonical_columns:
            language_values = _safe_duckdb_df(
                conn, "SELECT DISTINCT language FROM canonical WHERE language IS NOT NULL ORDER BY language"
            )["language"].dropna().tolist()
        if "year" in canonical_columns:
            year_values = (
                _safe_duckdb_df(conn, "SELECT DISTINCT year FROM canonical WHERE year IS NOT NULL ORDER BY year")
                .get("year", pd.Series(dtype="int"))
                .dropna()
                .tolist()
            )

        selected_sources = st.multiselect("Source", source_values, default=source_values)
        selected_languages = st.multiselect("Language", language_values, default=language_values)
        selected_years = st.multiselect("Year", year_values, default=year_values)

        st.divider()
        st.caption("Resolved storage paths")
        st.code(
            "\n".join(
                [
                    f"duckdb:   {paths.duckdb_path}",
                    f"sqlite:   {paths.sqlite_path}",
                    f"lancedb:  {paths.lance_path}",
                    f"graph:    {paths.networkx_graph_path}",
                ]
            ),
            language="text",
        )

    # Build canonical filters
    filter_parts = []
    if selected_sources and "source" in canonical_columns:
        vals = ", ".join([_sql_quote(v) for v in selected_sources])
        filter_parts.append(f"source IN ({vals})")
    if selected_languages and "language" in canonical_columns:
        vals = ", ".join([_sql_quote(v) for v in selected_languages])
        filter_parts.append(f"language IN ({vals})")
    if selected_years and "year" in canonical_columns:
        vals = ", ".join([str(int(v)) for v in selected_years])
        filter_parts.append(f"year IN ({vals})")
    canonical_where = f"WHERE {' AND '.join(filter_parts)}" if filter_parts else ""

    # Build chunks filters from canonical filter values
    chunk_filter_parts = []
    if selected_sources:
        source_col = "meta_source" if "meta_source" in chunks_columns else ("source" if "source" in chunks_columns else None)
        if source_col:
            vals = ", ".join([_sql_quote(v) for v in selected_sources])
            chunk_filter_parts.append(f"{source_col} IN ({vals})")
    if selected_languages:
        lang_col = "meta_language" if "meta_language" in chunks_columns else ("language" if "language" in chunks_columns else None)
        if lang_col:
            vals = ", ".join([_sql_quote(v) for v in selected_languages])
            chunk_filter_parts.append(f"{lang_col} IN ({vals})")
    if selected_years:
        year_col = "meta_year" if "meta_year" in chunks_columns else ("year" if "year" in chunks_columns else None)
        if year_col:
            vals = ", ".join([str(int(v)) for v in selected_years])
            chunk_filter_parts.append(f"{year_col} IN ({vals})")
    chunks_where = f"WHERE {' AND '.join(chunk_filter_parts)}" if chunk_filter_parts else ""

    # Top KPI row
    canonical_count = _safe_duckdb_df(conn, f"SELECT COUNT(*) AS c FROM canonical {canonical_where}")
    chunk_count_duck = _safe_duckdb_df(conn, f"SELECT COUNT(*) AS c FROM chunks {chunks_where}")
    sqlite_runs = _count_sqlite_table_rows(paths.sqlite_path, "pipeline_runs")
    sqlite_hashes = _count_sqlite_table_rows(paths.sqlite_path, "seen_hashes")

    db, lance_table = _open_lancedb(paths)
    lance_count = None
    if lance_table is not None:
        try:
            lance_count = len(lance_table)
        except Exception:
            lance_count = None

    graph_file_mb = _graph_file_size_mb(paths.networkx_graph_path)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Canonical rows", _format_number(int(canonical_count["c"].iloc[0]) if not canonical_count.empty else None))
    c2.metric("Chunk rows (Parquet)", _format_number(int(chunk_count_duck["c"].iloc[0]) if not chunk_count_duck.empty else None))
    c3.metric("Lance rows", _format_number(lance_count))
    c4.metric("Pipeline runs", _format_number(sqlite_runs))
    c5.metric("Graph backend", paths.graph_backend)
    c6.metric("Graph file (MB)", _format_number(graph_file_mb))

    tabs = st.tabs(["Request Metrics", "Dataset", "Pipeline", "Vector Index", "Graph", "SQL Explorer"])

    # ── Request Metrics tab ──────────────────────────────────────────────────
    with tabs[0]:
        st.subheader("Request Latency Metrics")
        st.caption("Per-stage latency breakdown from brain module trace files.")

        trace_files = sorted(paths.trace_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if paths.trace_dir.exists() else []
        max_traces = st.slider("Max traces to load", 50, 2000, 500, step=50, key="trace_limit")
        trace_files = trace_files[:max_traces]

        if not trace_files:
            st.info(f"No trace files found in `{paths.trace_dir}`. Run some queries against the brain API to generate traces.")
        else:
            traces_data: list[dict[str, Any]] = []
            for tf in trace_files:
                try:
                    raw = json.loads(tf.read_text())
                    flat: dict[str, Any] = {
                        "timestamp": raw.get("timestamp", ""),
                        "question": (raw.get("question", "") or "")[:80],
                        "from_cache": bool(raw.get("from_cache", False)),
                        "intent": (raw.get("routing") or {}).get("intent", ""),
                        "complexity": (raw.get("routing") or {}).get("complexity", 0),
                        "sources_count": (raw.get("response") or {}).get("sources_count", 0),
                        "confidence": (raw.get("response") or {}).get("confidence", 0),
                    }
                    timings = raw.get("timings_ms") or {}
                    for stage in ["routing", "cache_lookup", "parallel_fetch", "aggregate", "rerank", "synthesis", "total"]:
                        flat[f"t_{stage}"] = timings.get(stage, None)
                    traces_data.append(flat)
                except Exception:
                    continue

            if traces_data:
                tdf = pd.DataFrame(traces_data)
                tdf["timestamp"] = pd.to_datetime(tdf["timestamp"], errors="coerce")
                tdf = tdf.sort_values("timestamp", ascending=False).reset_index(drop=True)

                # KPI cards
                non_cache = tdf[~tdf["from_cache"]]
                kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
                kpi1.metric("Total requests", len(tdf))
                cache_pct = tdf["from_cache"].mean() * 100 if len(tdf) else 0
                kpi2.metric("Cache hit rate", f"{cache_pct:.1f}%")

                if not non_cache.empty and non_cache["t_total"].notna().any():
                    total_vals = non_cache["t_total"].dropna()
                    kpi3.metric("P50 latency", f"{total_vals.quantile(0.5):.0f} ms")
                    kpi4.metric("P95 latency", f"{total_vals.quantile(0.95):.0f} ms")
                    kpi5.metric("P99 latency", f"{total_vals.quantile(0.99):.0f} ms")
                else:
                    kpi3.metric("P50 latency", "n/a")
                    kpi4.metric("P95 latency", "n/a")
                    kpi5.metric("P99 latency", "n/a")

                # Per-stage latency breakdown (box plot)
                stage_cols = ["t_routing", "t_cache_lookup", "t_parallel_fetch", "t_aggregate", "t_rerank", "t_synthesis"]
                stage_labels = ["Routing", "Cache", "Fetch", "Aggregate", "Rerank", "Synthesis"]
                available_stages = [(col, label) for col, label in zip(stage_cols, stage_labels) if col in non_cache.columns and non_cache[col].notna().any()]

                if available_stages:
                    melt_df = non_cache[[c for c, _ in available_stages]].rename(
                        columns={c: l for c, l in available_stages}
                    ).melt(var_name="Stage", value_name="Latency (ms)")
                    melt_df = melt_df.dropna()
                    fig = px.box(
                        melt_df, x="Stage", y="Latency (ms)", color="Stage",
                        title="Per-stage latency distribution (non-cached)",
                        points="outliers",
                    )
                    fig.update_layout(showlegend=False)
                    _plot(fig)

                # Stacked area: stage latency over time
                if not non_cache.empty and "timestamp" in non_cache.columns:
                    time_sorted = non_cache.dropna(subset=["timestamp"]).sort_values("timestamp")
                    if len(time_sorted) > 5 and available_stages:
                        stage_time_df = time_sorted[["timestamp"] + [c for c, _ in available_stages]].rename(
                            columns={c: l for c, l in available_stages}
                        )
                        stage_time_melted = stage_time_df.melt(id_vars=["timestamp"], var_name="Stage", value_name="ms")
                        stage_time_melted = stage_time_melted.dropna()
                        fig = px.area(
                            stage_time_melted, x="timestamp", y="ms", color="Stage",
                            title="Latency breakdown over time",
                        )
                        _plot(fig)

                # Total latency timeline
                if not non_cache.empty and non_cache["t_total"].notna().any():
                    timeline_df = non_cache.dropna(subset=["timestamp", "t_total"]).sort_values("timestamp")
                    if not timeline_df.empty:
                        fig = px.scatter(
                            timeline_df, x="timestamp", y="t_total",
                            color="intent", size="sources_count",
                            hover_data=["question", "confidence"],
                            title="Total request latency over time",
                            opacity=0.7,
                        )
                        _plot(fig)

                # Intent breakdown
                if "intent" in tdf.columns and tdf["intent"].notna().any():
                    intent_left, intent_right = st.columns(2)
                    with intent_left:
                        intent_df = tdf["intent"].value_counts().reset_index()
                        intent_df.columns = ["intent", "count"]
                        fig = px.pie(intent_df, values="count", names="intent", title="Query intent distribution")
                        _plot(fig)
                    with intent_right:
                        if not non_cache.empty and "intent" in non_cache.columns and non_cache["t_total"].notna().any():
                            fig = px.box(
                                non_cache.dropna(subset=["t_total"]),
                                x="intent", y="t_total", color="intent",
                                title="Latency by intent type", points="outliers",
                            )
                            fig.update_layout(showlegend=False)
                            _plot(fig)

                # Recent requests table
                with st.expander("Recent requests", expanded=False):
                    display_cols_trace = [c for c in ["timestamp", "question", "intent", "from_cache", "t_total", "sources_count", "confidence"] if c in tdf.columns]
                    _table(tdf[display_cols_trace].head(100))
            else:
                st.info("Trace files found but could not parse any.")

    with tabs[1]:
        st.subheader("Dataset Profile (DuckDB over Parquet)")
        st.caption("Use sampling + chart mode controls for deeper, faster interaction.")

        ctrl1, ctrl2, ctrl3 = st.columns([1, 1, 1.5])
        with ctrl1:
            dataset_chart_mode = st.radio(
                "Distribution chart",
                ["bar", "treemap", "sunburst"],
                horizontal=True,
            )
        with ctrl2:
            scatter_sample_limit = st.slider("Scatter sample", 1000, 120000, 20000, step=1000)
        with ctrl3:
            top_n_tags = st.slider("Top tags", 10, 80, 30, step=5)

        left, right = st.columns(2)
        with left:
            if "source" in canonical_columns:
                source_df = _safe_duckdb_df(
                    conn,
                    f"""
                    SELECT source, COUNT(*) AS count
                    FROM canonical
                    {canonical_where}
                    GROUP BY source
                    ORDER BY count DESC
                    """,
                )
                if not source_df.empty:
                    if dataset_chart_mode == "bar":
                        fig = px.bar(source_df, x="source", y="count", title="Records by source")
                    elif dataset_chart_mode == "treemap":
                        fig = px.treemap(source_df, path=["source"], values="count", title="Records by source (treemap)")
                    else:
                        fig = px.sunburst(source_df, path=["source"], values="count", title="Records by source (sunburst)")
                    _plot(fig)
                else:
                    st.info("No source distribution available yet.")
            else:
                st.info("`source` column not present in canonical table.")

        with right:
            if "year" in canonical_columns and "source" in canonical_columns:
                year_df = _safe_duckdb_df(
                    conn,
                    _with_filter(
                        """
                        SELECT year, source, COUNT(*) AS count
                        FROM canonical
                        {where}
                        GROUP BY year, source
                        ORDER BY year, source
                        """,
                        canonical_where,
                    ),
                )
                if not year_df.empty:
                    fig = px.density_heatmap(
                        year_df,
                        x="year",
                        y="source",
                        z="count",
                        histfunc="sum",
                        title="Source vs year intensity",
                        color_continuous_scale="Blues",
                    )
                    _plot(fig)
                else:
                    st.info("No year/source density available yet.")
            elif "year" in canonical_columns:
                year_df = _safe_duckdb_df(
                    conn,
                    f"""
                    SELECT year, COUNT(*) AS count
                    FROM canonical
                    {canonical_where}
                    GROUP BY year
                    ORDER BY year
                    """,
                )
                if not year_df.empty:
                    fig = px.line(year_df, x="year", y="count", markers=True, title="Records over time")
                    _plot(fig)
                else:
                    st.info("No year trend available yet.")
            else:
                st.info("`year` column not present in canonical table.")

        lower_left, lower_right = st.columns(2)
        with lower_left:
            if "tags" in canonical_columns:
                tags_df = _safe_duckdb_df(
                    conn,
                    f"""
                    SELECT tag, COUNT(*) AS freq
                    FROM (
                      SELECT unnest(string_split(tags, ',')) AS tag
                      FROM canonical
                      {canonical_where}
                    )
                    WHERE tag IS NOT NULL AND trim(tag) <> ''
                    GROUP BY tag
                    ORDER BY freq DESC
                    LIMIT {top_n_tags}
                    """,
                )
                if not tags_df.empty:
                    fig = px.bar(tags_df, x="freq", y="tag", orientation="h", title="Top tags")
                    fig.update_layout(yaxis={"categoryorder": "total ascending"})
                    _plot(fig)
                else:
                    st.info("No tags available.")
            else:
                st.info("`tags` column not present in canonical table.")

        with lower_right:
            score_col = _coalesce_cols(canonical_columns, "score")
            if score_col:
                score_df = _safe_duckdb_df(
                    conn,
                    f"""
                    SELECT FLOOR({score_col} / 10) * 10 AS score_bucket, COUNT(*) AS count
                    FROM canonical
                    {canonical_where}
                    GROUP BY score_bucket
                    ORDER BY score_bucket
                    """,
                )
                if not score_df.empty:
                    fig = px.bar(score_df, x="score_bucket", y="count", title="Score distribution (bucketed)")
                    _plot(fig)
                else:
                    st.info("No score distribution available.")
            else:
                st.info("`score` column not present in canonical table.")

        st.markdown("### Interactive scatter explorer")
        numeric_choices = [c for c in ["score", "answer_count", "view_count", "year"] if c in canonical_columns]
        color_choices = [c for c in ["source", "language"] if c in canonical_columns]
        if len(numeric_choices) >= 2:
            s1, s2, s3 = st.columns(3)
            with s1:
                x_axis = st.selectbox("X-axis", numeric_choices, index=0)
            with s2:
                y_axis = st.selectbox("Y-axis", numeric_choices, index=min(1, len(numeric_choices) - 1))
            with s3:
                color_axis = st.selectbox("Color", color_choices or ["source"], index=0 if color_choices else None)

            select_cols = [x_axis, y_axis]
            if color_axis in canonical_columns:
                select_cols.append(color_axis)
            if "source" in canonical_columns and "source" not in select_cols:
                select_cols.append("source")
            if "title" in canonical_columns:
                select_cols.append("title")
            elif "question" in canonical_columns:
                select_cols.append("question")
            select_cols_sql = ", ".join(select_cols)

            scatter_df = _safe_duckdb_df(
                conn,
                f"""
                SELECT {select_cols_sql}
                FROM canonical
                {canonical_where}
                ORDER BY random()
                LIMIT {scatter_sample_limit}
                """,
            )
            if not scatter_df.empty:
                hover_col = "title" if "title" in scatter_df.columns else ("question" if "question" in scatter_df.columns else None)
                fig = px.scatter(
                    scatter_df,
                    x=x_axis,
                    y=y_axis,
                    color=color_axis if color_axis in scatter_df.columns else None,
                    hover_data=[hover_col] if hover_col else None,
                    title=f"{y_axis} vs {x_axis} (sampled)",
                    opacity=0.55,
                )
                _plot(fig)
                with st.expander("Sample rows used in scatter", expanded=False):
                    _table(scatter_df.head(200))
            else:
                st.info("No rows for scatter explorer with current filters.")
        else:
            st.info("Need at least two numeric columns (`score`, `answer_count`, `view_count`, `year`) for scatter explorer.")

    with tabs[2]:
        st.subheader("Pipeline State (SQLite)")
        if not paths.sqlite_path.exists():
            st.warning(f"SQLite DB not found at: {paths.sqlite_path}")
        else:
            sql_conn = sqlite3.connect(str(paths.sqlite_path))
            sql_conn.row_factory = sqlite3.Row

            def read_sql(table: str) -> pd.DataFrame:
                try:
                    return pd.read_sql_query(f"SELECT * FROM {table}", sql_conn)
                except Exception:
                    return pd.DataFrame()

            runs_df = read_sql("pipeline_runs")
            checkpoints_df = read_sql("source_checkpoints")
            downloads_df = read_sql("download_status")

            if not runs_df.empty:
                # Enrich run rows with durations and throughput when possible.
                if "started_at" in runs_df.columns:
                    runs_df["started_at_dt"] = pd.to_datetime(runs_df["started_at"], errors="coerce")
                if "finished_at" in runs_df.columns:
                    runs_df["finished_at_dt"] = pd.to_datetime(runs_df["finished_at"], errors="coerce")
                if "started_at_dt" in runs_df.columns and "finished_at_dt" in runs_df.columns:
                    runs_df["duration_sec"] = (
                        runs_df["finished_at_dt"] - runs_df["started_at_dt"]
                    ).dt.total_seconds()
                    if "records_out" in runs_df.columns:
                        runs_df["throughput_rps"] = runs_df["records_out"] / runs_df["duration_sec"].clip(lower=1)

                st.markdown("**Recent runs**")
                display_cols = [c for c in ["run_id", "source", "status", "records_in", "records_out", "started_at", "finished_at"] if c in runs_df.columns]
                _table(runs_df.sort_values("run_id", ascending=False)[display_cols].head(50))

                p1, p2 = st.columns(2)
                with p1:
                    if "status" in runs_df.columns:
                        status_df = runs_df.groupby("status", as_index=False).size()
                        fig = px.pie(status_df, values="size", names="status", title="Run status mix")
                        _plot(fig)
                with p2:
                    if "source" in runs_df.columns:
                        src_df = runs_df.groupby("source", as_index=False).size().sort_values("size", ascending=False)
                        fig = px.bar(src_df, x="source", y="size", title="Runs by source")
                        _plot(fig)

                if {"started_at_dt", "duration_sec", "source"}.issubset(set(runs_df.columns)):
                    timeline_df = runs_df.dropna(subset=["started_at_dt", "duration_sec"]).copy()
                    if not timeline_df.empty:
                        timeline_df["duration_sec"] = timeline_df["duration_sec"].clip(lower=0)
                        fig = px.scatter(
                            timeline_df.sort_values("started_at_dt"),
                            x="started_at_dt",
                            y="duration_sec",
                            color="source",
                            size="duration_sec",
                            hover_data=[c for c in ["run_id", "status", "records_in", "records_out"] if c in timeline_df.columns],
                            title="Run duration over time",
                            opacity=0.75,
                        )
                        _plot(fig)

                if {"source", "throughput_rps"}.issubset(set(runs_df.columns)):
                    tp_df = runs_df.dropna(subset=["throughput_rps"]).copy()
                    if not tp_df.empty:
                        fig = px.box(
                            tp_df,
                            x="source",
                            y="throughput_rps",
                            color="source",
                            points="all",
                            title="Throughput distribution by source (records/sec)",
                        )
                        _plot(fig)
            else:
                st.info("No `pipeline_runs` rows yet.")

            if not checkpoints_df.empty:
                st.markdown("**Source checkpoints**")
                _table(checkpoints_df)

            if not downloads_df.empty:
                st.markdown("**Download status**")
                _table(downloads_df.sort_values(["source", "filename"]))

            sql_conn.close()

    with tabs[3]:
        st.subheader("Vector Index (LanceDB + Chunk metadata)")
        if db is None:
            st.warning(f"LanceDB path not available or unreadable: {paths.lance_path}")
        else:
            table_names = _lance_table_names(db)
            st.caption(f"Lance tables: {', '.join(table_names) if table_names else 'none'}")
            if lance_table is None:
                st.info(f"Table `{paths.lance_table}` not found in LanceDB.")
            else:
                st.success(f"Connected to LanceDB table `{paths.lance_table}`")
                st.metric("Lance row count", _format_number(lance_count))

        # Additional vector-friendly profiling from chunk parquet view.
        if chunks_columns:
            st.caption("Interactive profiling across chunk source/type/token behavior.")
            col_a, col_b = st.columns(2)
            with col_a:
                chunk_type_col = "chunk_type" if "chunk_type" in chunks_columns else None
                if chunk_type_col:
                    chunk_types_df = _safe_duckdb_df(
                        conn,
                        f"""
                        SELECT {chunk_type_col} AS chunk_type, COUNT(*) AS count
                        FROM chunks
                        {chunks_where}
                        GROUP BY {chunk_type_col}
                        ORDER BY count DESC
                        """,
                    )
                    if not chunk_types_df.empty:
                        fig = px.bar(chunk_types_df, x="chunk_type", y="count", title="Chunk type mix")
                        _plot(fig)
            with col_b:
                token_col = "token_count" if "token_count" in chunks_columns else None
                if token_col:
                    tokens_df = _safe_duckdb_df(
                        conn,
                        f"""
                        SELECT {token_col} AS token_count
                        FROM chunks
                        {chunks_where}
                        LIMIT 50000
                        """,
                    )
                    if not tokens_df.empty:
                        fig = px.histogram(tokens_df, x="token_count", nbins=40, title="Token count distribution (sample)")
                        _plot(fig)

            meta_source_col = "meta_source" if "meta_source" in chunks_columns else None
            if meta_source_col:
                meta_source_df = _safe_duckdb_df(
                    conn,
                    f"""
                    SELECT {meta_source_col} AS source, COUNT(*) AS count
                    FROM chunks
                    {chunks_where}
                    GROUP BY {meta_source_col}
                    ORDER BY count DESC
                    """,
                )
                if not meta_source_df.empty:
                    fig = px.bar(meta_source_df, x="source", y="count", title="Chunk source distribution")
                    _plot(fig)

            # Richer interaction: source x chunk_type heatmap + token boxplot by source.
            chunk_type_col = _coalesce_cols(chunks_columns, "chunk_type")
            token_col = _coalesce_cols(chunks_columns, "token_count")
            meta_source_col = _coalesce_cols(chunks_columns, "meta_source", "source")
            policy_col = _coalesce_cols(chunks_columns, "meta_chunking_policy")

            if chunk_type_col and meta_source_col:
                mix_df = _safe_duckdb_df(
                    conn,
                    f"""
                    SELECT {meta_source_col} AS source, {chunk_type_col} AS chunk_type, COUNT(*) AS count
                    FROM chunks
                    {chunks_where}
                    GROUP BY {meta_source_col}, {chunk_type_col}
                    ORDER BY count DESC
                    """,
                )
                if not mix_df.empty:
                    fig = px.density_heatmap(
                        mix_df,
                        x="source",
                        y="chunk_type",
                        z="count",
                        histfunc="sum",
                        title="Chunk type intensity by source",
                        color_continuous_scale="Viridis",
                    )
                    _plot(fig)

            if token_col and meta_source_col:
                token_box_df = _safe_duckdb_df(
                    conn,
                    f"""
                    SELECT {meta_source_col} AS source, {token_col} AS token_count
                    FROM chunks
                    {chunks_where}
                    LIMIT 60000
                    """,
                )
                if not token_box_df.empty:
                    fig = px.box(
                        token_box_df,
                        x="source",
                        y="token_count",
                        color="source",
                        points="outliers",
                        title="Token count spread by source",
                    )
                    _plot(fig)

            if policy_col:
                policy_df = _safe_duckdb_df(
                    conn,
                    f"""
                    SELECT {policy_col} AS policy, COUNT(*) AS count
                    FROM chunks
                    {chunks_where}
                    GROUP BY {policy_col}
                    ORDER BY count DESC
                    """,
                )
                if not policy_df.empty:
                    fig = px.treemap(policy_df, path=["policy"], values="count", title="Chunking policy footprint")
                    _plot(fig)
        else:
            st.info("Chunks table/view is unavailable.")

    with tabs[4]:
        st.subheader("Graph Store")
        st.caption(f"Configured backend: `{paths.graph_backend}`")
        load_graph = st.toggle("Load graph analytics", value=False, help="Enable this only when exploring graph data.")
        graph_obj = _load_networkx_graph(paths.networkx_graph_path) if load_graph else None
        if graph_obj is None:
            if load_graph:
                st.info("No local NetworkX graph found (or failed to load).")
                st.caption("If you use Neo4j in prod, add a small Cypher metrics adapter in a next iteration.")
            else:
                st.info("Graph analytics is paused for faster page loads. Toggle it on when needed.")
        else:
            g = graph_obj
            left, right = st.columns(2)
            with left:
                st.metric("Nodes", _format_number(g.number_of_nodes()))
            with right:
                st.metric("Edges", _format_number(g.number_of_edges()))

            graph_ctrl1, graph_ctrl2 = st.columns([1.4, 1])
            with graph_ctrl1:
                layout_engine = st.selectbox("Layout engine", ["spring", "kamada_kawai", "circular"], index=0)
            with graph_ctrl2:
                render_limit = st.slider("Neighborhood max nodes", 40, 300, 140, step=20)

            # Top entities by degree: sampled for responsiveness on large graphs.
            sample_limit = st.slider("Max nodes to sample for degree ranking", 500, 20000, 5000, step=500)
            sampled_nodes = []
            for idx, node in enumerate(g.nodes()):
                sampled_nodes.append(node)
                if idx + 1 >= sample_limit:
                    break
            degree_df = (
                pd.DataFrame(
                    [(node, int(g.degree(node))) for node in sampled_nodes],
                    columns=["node", "degree"],
                )
                .sort_values("degree", ascending=False)
                .head(25)
            )
            if not degree_df.empty:
                fig = px.bar(degree_df, x="degree", y="node", orientation="h", title="Top degree nodes")
                fig.update_layout(yaxis={"categoryorder": "total ascending"})
                _plot(fig)

            # Edge predicate/activity snapshot from sampled edges for quick structure insight.
            edge_sample_limit = st.slider("Edge sample for relation stats", 500, 30000, 5000, step=500)
            edge_sample = []
            for idx, (_, _, _, data) in enumerate(g.edges(keys=True, data=True)):
                edge_sample.append(data)
                if idx + 1 >= edge_sample_limit:
                    break
            if edge_sample:
                pred_df = pd.DataFrame(edge_sample)
                if "predicate" in pred_df.columns:
                    pred_df = pred_df["predicate"].fillna("unknown").value_counts().reset_index()
                    pred_df.columns = ["predicate", "count"]
                    fig = px.pie(pred_df, values="count", names="predicate", title="Relation type mix (sampled)")
                    _plot(fig)

            st.markdown("**Local neighborhood explorer**")
            seed = st.text_input("Seed node id", value=str(degree_df["node"].iloc[0]) if not degree_df.empty else "")
            depth = st.slider("Hop depth", min_value=1, max_value=3, value=1)

            if seed:
                try:
                    import networkx as nx

                    # Undirected ego graph for quick visual understanding.
                    sub = nx.ego_graph(g.to_undirected(), seed, radius=depth)
                    if sub.number_of_nodes() > render_limit:
                        st.warning(f"Subgraph too large to render nicely; showing first {render_limit} nodes.")
                        nodes = list(sub.nodes())[:render_limit]
                        sub = sub.subgraph(nodes)

                    if layout_engine == "kamada_kawai":
                        pos = nx.kamada_kawai_layout(sub)
                    elif layout_engine == "circular":
                        pos = nx.circular_layout(sub)
                    else:
                        pos = nx.spring_layout(sub, seed=42)
                    edge_x, edge_y = [], []
                    for u, v in sub.edges():
                        x0, y0 = pos[u]
                        x1, y1 = pos[v]
                        edge_x += [x0, x1, None]
                        edge_y += [y0, y1, None]

                    node_x, node_y, node_text, node_degree = [], [], [], []
                    for n in sub.nodes():
                        x, y = pos[n]
                        node_x.append(x)
                        node_y.append(y)
                        node_text.append(str(n))
                        node_degree.append(int(sub.degree(n)))

                    edge_fig = px.line(x=edge_x, y=edge_y)
                    edge_fig.update_traces(line={"width": 1}, hoverinfo="none")
                    node_fig = px.scatter(
                        x=node_x,
                        y=node_y,
                        hover_name=node_text,
                        size=node_degree,
                        color=node_degree,
                        color_continuous_scale="Turbo",
                    )
                    node_fig.update_traces(marker={"line": {"width": 0.4, "color": "#1f2937"}})

                    fig = edge_fig
                    for trace in node_fig.data:
                        fig.add_trace(trace)
                    fig.update_layout(
                        title=f"Neighborhood graph around `{seed}` (depth={depth})",
                        xaxis={"visible": False},
                        yaxis={"visible": False},
                        showlegend=False,
                        margin={"l": 10, "r": 10, "t": 50, "b": 10},
                    )
                    _plot(fig)
                except Exception as exc:
                    st.error(f"Could not render subgraph: {exc}")

    with tabs[5]:
        st.subheader("SQL Explorer (DuckDB)")
        st.caption("Run read-only analytical queries over registered `canonical` and `chunks` views.")
        default_query = "SELECT source, COUNT(*) AS count FROM canonical GROUP BY source ORDER BY count DESC LIMIT 25;"
        query = st.text_area("SQL", value=default_query, height=120)
        if st.button("Run query", type="primary"):
            out = _safe_duckdb_df(conn, query)
            if out.empty:
                st.info("No rows returned (or query failed).")
            else:
                _table(out)

    st.divider()
    st.caption(
        "Tip: start with `Dataset` and `Pipeline` tabs for operational health, then drill into `Vector Index` and `Graph`."
    )


if __name__ == "__main__":
    main()
