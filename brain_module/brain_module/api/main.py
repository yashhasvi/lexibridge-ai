"""
Brain Module FastAPI application.

Endpoints
---------
POST /ask               → full BrainResponse JSON
POST /ask/stream        → SSE token stream from the LLM
GET  /health            → liveness
GET  /sources           → list of registered fetchers
POST /evaluate          → Ragas evaluation of a BrainResponse
POST /ingest/lightrag   → ingest CanonicalQA JSON list into LightRAG
POST /generate-answer   → Pebble UI: same as /ask + frontend-shaped sources
POST /detect-language   → ISO 639-1 via langdetect (text queries)
POST /translate         → LLM translation (answers back to user language)
POST /audio/transcribe  → Whisper upload (chunked or simple; needs PYTHONPATH + whisper)

Environment variables
---------------------
LLM_BACKEND         : openai | ollama | vllm | tgi | litellm  (default: ollama)
LLM_MODEL           : model name
OPENAI_API_KEY      : required for openai backend
LIGHTRAG_URL        : LightRAG server base URL  (default: http://localhost:9621)
REDIS_URL           : optional Redis URL for caching
RERANKER_MODEL      : cross-encoder model name
SEMANTIC_DEDUP      : "true" to enable semantic dedup (slower)

Guardrail environment variables
-------------------------------
MIN_RERANK_SCORE    : minimum cross-encoder score to keep a chunk  (default: 0.15)
MAX_SAME_SOURCE     : max chunks from one source in synthesis      (default: 2)
LOW_CONFIDENCE_THRESHOLD : avg score below which to inject prompt hint (default: 0.3)
ENABLE_LLM_JUDGE    : enable optional LLM-as-judge second-pass     (default: false)
GUARDRAIL_STRICT_MODE : replace (not disclaim) on guardrail fail   (default: false)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()  # reads .env from cwd (or any parent dir)
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..aggregation import MultiSourceAggregator
from ..cache.embedding_cache import EmbeddingCache
from ..cache.query_cache import QueryCache
from ..cache.semantic_cache import SemanticCache
from ..compression.sentence_compressor import SentenceCompressor
from ..evaluation.ragas_eval import RagasEvaluator
from ..query.rewriter import QueryRewriter
from ..reranking.cross_encoder import CrossEncoderReranker
from ..response.formatter import ResponseFormatter
from ..response.schema import BrainResponse
from ..retrieval.fetcher_registry import FetcherRegistry, LightRAGFetcher
from ..retrieval.lightrag_adapter import LightRAGClient, LightRAGIngestionAdapter
from ..retrieval.parallel_runner import ParallelFetcher
from ..router import QueryRouter
from ..synthesis import SynthesisEngine
from ..synthesis.llm_client import create_llm_client, create_tiered_llm_client, TieredLLMClient

from .audio_routes import router as audio_router

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# data_module fetcher wiring
# --------------------------------------------------------------------------- #

def _register_data_module_fetchers(
    registry: FetcherRegistry,
    *,
    eager_bm25_load: bool = True,
    embedding_cache_enabled: bool = True,
    embedding_cache_maxsize: int = 2048,
) -> None:
    """
    Initialise FastRAGFetcher, HybridFetcher, and GraphRAGFetcher from the
    paths declared in .env and register them into `registry`.

    Failures are logged as warnings rather than crashing the server — the
    brain pipeline degrades gracefully with fewer fetchers.
    """
    from pathlib import Path

    lance_path = os.getenv("LANCE_DB_PATH", "")
    graph_path = os.getenv("GRAPH_PATH", "")
    parquet_chunks_dir = os.getenv("PARQUET_PATH", "")
    embedding_model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    embedding_device = os.getenv("EMBEDDING_DEVICE", "cpu")
    table_name = os.getenv("LANCE_TABLE", "chunks")

    if not lance_path:
        logger.warning("LANCE_DB_PATH not set — fast_rag and hybrid fetchers disabled.")
        return

    lance_store = None

    # ── FastRAGFetcher ────────────────────────────────────────────────────────
    try:
        from data_module.storage.lance_store import LanceStore
        from data_module.fetch.fast_rag import FastRAGFetcher

        lance_store = LanceStore(
            db_path=Path(lance_path),
            table_name=table_name,
        )
        fast_rag = FastRAGFetcher(
            lance_store=lance_store,
            embedding_model=embedding_model,
            device=embedding_device,
        )

        if embedding_cache_enabled:
            fast_rag._embedder = EmbeddingCache(
                fast_rag._embedder,
                maxsize=embedding_cache_maxsize,
                enabled=True,
            )
            logger.info("Embedding cache enabled for FastRAGFetcher (maxsize=%d)", embedding_cache_maxsize)

        registry.register("fast_rag", fast_rag)
        logger.info("FastRAGFetcher registered (LanceDB: %s)", lance_path)
    except Exception as exc:
        logger.warning("FastRAGFetcher init failed: %s", exc, exc_info=True)
        return  # both downstream fetchers depend on this

    # ── HybridFetcher (BM25 + dense) ─────────────────────────────────────────
    try:
        from data_module.fetch.hybrid import HybridFetcher

        hybrid = HybridFetcher(dense_fetcher=fast_rag)

        if eager_bm25_load and parquet_chunks_dir and Path(parquet_chunks_dir).exists():
            from data_module.storage.parquet_store import ParquetStore
            # canonical_dir sits one level up from chunks_dir
            canonical_dir = Path(parquet_chunks_dir).parent / "canonical"
            parquet_store = ParquetStore(
                canonical_dir=canonical_dir,
                chunks_dir=Path(parquet_chunks_dir),
            )
            hybrid.load_texts_from_parquet(parquet_store)
            logger.info("HybridFetcher BM25 index built from %s", parquet_chunks_dir)
        elif not eager_bm25_load:
            logger.info("HybridFetcher BM25 eager-load disabled.")
        else:
            logger.warning("PARQUET_PATH not set or missing — HybridFetcher runs dense-only.")

        registry.register("hybrid", hybrid)
        logger.info("HybridFetcher registered.")
    except Exception as exc:
        logger.warning("HybridFetcher init failed: %s", exc, exc_info=True)

    # ── GraphRAGFetcher ───────────────────────────────────────────────────────
    graph_backend = os.getenv("GRAPH_BACKEND", "neo4j")

    try:
        from data_module.fetch.graph_rag import GraphRAGFetcher
        from data_module.storage.graph_store import get_graph_store

        graph_cfg: dict[str, str] = {"backend": graph_backend}

        if graph_backend == "neo4j":
            graph_cfg["neo4j_uri"] = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            graph_cfg["neo4j_user"] = os.getenv("NEO4J_USER", "neo4j")
            graph_cfg["neo4j_password"] = os.getenv("NEO4J_PASSWORD", "specialNeo123$")
            logger.info("GraphRAGFetcher: using Neo4j backend at %s", graph_cfg["neo4j_uri"])
        else:
            if not graph_path or not Path(graph_path).exists():
                logger.warning("GRAPH_PATH not set or missing — graph_rag fetcher disabled.")
                return
            graph_cfg["networkx_path"] = graph_path
            logger.info("GraphRAGFetcher: using NetworkX backend from %s", graph_path)

        graph_store = get_graph_store(graph_cfg)
        graph_rag = GraphRAGFetcher(
            lance_store=lance_store,
            graph_store=graph_store,
            embedding_model=embedding_model,
            device=embedding_device,
        )
        registry.register("graph_rag", graph_rag)
        logger.info("GraphRAGFetcher registered (backend: %s)", graph_backend)
    except Exception as exc:
        logger.warning("GraphRAGFetcher init failed: %s", exc, exc_info=True)



# --------------------------------------------------------------------------- #
# Application state (initialised at startup)
# --------------------------------------------------------------------------- #

class AppState:
    registry: FetcherRegistry
    router: QueryRouter
    parallel_fetcher: ParallelFetcher
    aggregator: MultiSourceAggregator
    reranker: CrossEncoderReranker
    synthesis_engine: SynthesisEngine
    cache: QueryCache
    semantic_cache: SemanticCache | None
    evaluator: RagasEvaluator
    lightrag_client: LightRAGClient
    query_rewriter: QueryRewriter
    context_compressor: SentenceCompressor
    retrieval_expansion_factor: float
    rerank_bypass_complexity_threshold: float
    adaptive_pipeline_enabled: bool
    fast_path_enabled: bool
    adaptive_complexity_threshold: float
    early_stop_retrieval_enabled: bool
    early_stop_confidence_threshold: float
    fast_path_max_rewrite_variants: int
    fast_path_skip_rerank: bool
    fast_path_expansion_factor: float
    fast_path_top_n_context: int
    fast_path_max_synth_tokens: int
    trace_dir: Path
    trace_enabled: bool


_state = AppState()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _safe_int_env(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        logger.warning("Invalid %s=%r. Falling back to %d.", name, raw, default)
        return default


def _safe_float_env(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, float(raw))
    except ValueError:
        logger.warning("Invalid %s=%r. Falling back to %.3f.", name, raw, default)
        return default


def _write_agentic_trace(trace_payload: dict[str, Any]) -> tuple[str, str] | tuple[None, None]:
    if not _state.trace_enabled:
        return None, None
    trace_id = str(uuid.uuid4())
    trace_file = _state.trace_dir / f"{trace_id}.json"
    trace_file.write_text(json.dumps(trace_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return trace_id, f"/traces/{trace_id}"


def _compute_pipeline_mode(plan: Any) -> str:
    if not (_state.adaptive_pipeline_enabled and _state.fast_path_enabled):
        return "deep"
    if plan.intent.value != "factual":
        return "deep"
    if plan.complexity_score > _state.adaptive_complexity_threshold:
        return "deep"
    return "fast"


def _compute_retrieval_confidence(chunks: list[dict[str, Any]]) -> float:
    if not chunks:
        return 0.0
    ranked = sorted(chunks, key=lambda c: float(c.get("score", 0.0)), reverse=True)
    top = ranked[:3]
    top_score = float(top[0].get("score", 0.0))
    avg_top = sum(float(c.get("score", 0.0)) for c in top) / max(len(top), 1)
    unique_sources = len({(c.get("source") or c.get("source_url") or "") for c in top if c})
    diversity = unique_sources / max(len(top), 1)
    return max(0.0, min(1.0, (0.55 * top_score) + (0.30 * avg_top) + (0.15 * diversity)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise all pipeline components at startup."""
    _state.retrieval_expansion_factor = _safe_float_env(
        "RETRIEVAL_EXPANSION_FACTOR", default=1.5, minimum=1.0
    )
    _state.rerank_bypass_complexity_threshold = _safe_float_env(
        "RERANK_BYPASS_COMPLEXITY_THRESHOLD", default=0.25, minimum=0.0
    )
    _state.adaptive_pipeline_enabled = _env_bool("ADAPTIVE_PIPELINE_ENABLED", False)
    _state.fast_path_enabled = _env_bool("FAST_PATH_ENABLED", False)
    _state.adaptive_complexity_threshold = _safe_float_env(
        "ADAPTIVE_COMPLEXITY_THRESHOLD", default=0.35, minimum=0.0
    )
    _state.early_stop_retrieval_enabled = _env_bool("EARLY_STOP_RETRIEVAL_ENABLED", False)
    _state.early_stop_confidence_threshold = _safe_float_env(
        "EARLY_STOP_CONFIDENCE_THRESHOLD", default=0.78, minimum=0.0
    )
    _state.fast_path_max_rewrite_variants = _safe_int_env(
        "FAST_PATH_MAX_REWRITE_VARIANTS", default=1, minimum=1
    )
    _state.fast_path_skip_rerank = _env_bool("FAST_PATH_SKIP_RERANK", True)
    _state.fast_path_expansion_factor = _safe_float_env(
        "FAST_PATH_RETRIEVAL_EXPANSION_FACTOR", default=1.0, minimum=1.0
    )
    _state.fast_path_top_n_context = _safe_int_env("FAST_PATH_TOP_N_CONTEXT", default=3, minimum=1)
    _state.fast_path_max_synth_tokens = _safe_int_env(
        "FAST_PATH_MAX_SYNTH_TOKENS", default=512, minimum=64
    )
    _state.trace_enabled = _env_bool("AGENTIC_TRACE_ENABLED", True)
    _state.trace_dir = Path(os.getenv("AGENTIC_TRACE_DIR", "/tmp/brain_module_traces"))
    _state.trace_dir.mkdir(parents=True, exist_ok=True)

    eager_bm25_load = _env_bool("HYBRID_BM25_EAGER_LOAD", True)
    top_n_before_rerank = _safe_int_env("TOP_N_BEFORE_RERANK", default=15, minimum=5)

    # --- LightRAG ---
    lightrag_url = os.getenv("LIGHTRAG_URL", "http://localhost:9621")
    _state.lightrag_client = LightRAGClient(base_url=lightrag_url)
    lightrag_alive = await _state.lightrag_client.health()
    if not lightrag_alive:
        logger.warning("LightRAG server not reachable at %s — LightRAG fetcher disabled.", lightrag_url)

    # --- Fetcher registry ---
    _state.registry = FetcherRegistry()
    if lightrag_alive:
        _state.registry.register("lightrag", LightRAGFetcher(_state.lightrag_client, mode="hybrid"))

    # --- Embedding cache config ---
    embedding_cache_enabled = _env_bool("EMBEDDING_CACHE_ENABLED", True)
    embedding_cache_maxsize = _safe_int_env("EMBEDDING_CACHE_MAXSIZE", default=2048, minimum=64)

    # --- data_module fetchers ---
    _register_data_module_fetchers(
        _state.registry,
        eager_bm25_load=eager_bm25_load,
        embedding_cache_enabled=embedding_cache_enabled,
        embedding_cache_maxsize=embedding_cache_maxsize,
    )

    # --- Pipeline components ---
    _state.router = QueryRouter()
    _state.parallel_fetcher = ParallelFetcher(_state.registry)

    semantic_dedup_threshold = (
        0.92 if os.getenv("SEMANTIC_DEDUP", "").lower() == "true" else None
    )
    _state.aggregator = MultiSourceAggregator(
        semantic_dedup_threshold=semantic_dedup_threshold,
        top_n_before_rerank=top_n_before_rerank,
    )

    reranker_model = os.getenv(
        "RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
    )
    _state.reranker = CrossEncoderReranker(model_name=reranker_model)

    llm_backend = os.getenv("LLM_BACKEND", "ollama")
    llm_model = os.getenv("LLM_MODEL", None)
    llm_model_fast = os.getenv("LLM_MODEL_FAST", None)
    llm_tiered_threshold = _safe_float_env("LLM_TIERED_THRESHOLD", default=0.35, minimum=0.0)
    llm_client = create_tiered_llm_client(
        backend=llm_backend,
        large_model=llm_model,
        fast_model=llm_model_fast,
        complexity_threshold=llm_tiered_threshold,
    )

    min_rerank_score = _safe_float_env("MIN_RERANK_SCORE", default=0.15, minimum=0.0)
    max_same_source = _safe_int_env("MAX_SAME_SOURCE", default=2, minimum=1)
    low_confidence_threshold = _safe_float_env("LOW_CONFIDENCE_THRESHOLD", default=0.3, minimum=0.0)
    guardrail_strict_mode = _env_bool("GUARDRAIL_STRICT_MODE", False)
    enable_llm_judge = _env_bool("ENABLE_LLM_JUDGE", False)

    # --- Context compressor (must be created before SynthesisEngine) ---
    compression_enabled = _env_bool("CONTEXT_COMPRESSION_ENABLED", True)
    compression_min_score = _safe_float_env("CONTEXT_COMPRESSION_MIN_SCORE", default=0.25, minimum=0.0)
    compression_top_sents = _safe_int_env("CONTEXT_COMPRESSION_TOP_SENTS", default=5, minimum=1)
    embedding_model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    embedding_device = os.getenv("EMBEDDING_DEVICE", "cpu")
    _state.context_compressor = SentenceCompressor(
        enabled=compression_enabled,
        min_similarity=compression_min_score,
        top_sentences_per_chunk=compression_top_sents,
        model_name=embedding_model,
        device=embedding_device,
    )

    _state.synthesis_engine = SynthesisEngine(
        llm_client=llm_client,
        reranker_model=reranker_model,
        min_rerank_score=min_rerank_score,
        max_same_source=max_same_source,
        low_confidence_threshold=low_confidence_threshold,
        guardrail_strict_mode=guardrail_strict_mode,
        enable_llm_judge=enable_llm_judge,
        context_compressor=_state.context_compressor,
    )

    # --- Query rewriter ---
    query_rewrite_enabled = _env_bool("QUERY_REWRITE_ENABLED", True)
    query_rewrite_max_variants = _safe_int_env("QUERY_REWRITE_MAX_VARIANTS", default=3, minimum=2)
    _state.query_rewriter = QueryRewriter(
        llm_client=llm_client,
        max_variants=query_rewrite_max_variants,
        enabled=query_rewrite_enabled,
    )

    _state.cache = QueryCache.from_env()

    # --- Semantic cache (embedding-similarity for near-duplicate queries) ---
    semantic_cache_enabled = _env_bool("SEMANTIC_CACHE_ENABLED", True)
    semantic_cache_threshold = _safe_float_env("SEMANTIC_CACHE_THRESHOLD", default=0.92, minimum=0.5)
    semantic_cache_maxsize = _safe_int_env("SEMANTIC_CACHE_MAXSIZE", default=1024, minimum=32)
    if semantic_cache_enabled:
        from data_module.pipelines.embed import get_embedder as _get_embedder
        _sem_embedder = _get_embedder(
            os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            os.getenv("EMBEDDING_DEVICE", "cpu"),
        )
        _state.semantic_cache = SemanticCache(
            embedder=_sem_embedder,
            threshold=semantic_cache_threshold,
            maxsize=semantic_cache_maxsize,
            enabled=True,
        )
    else:
        _state.semantic_cache = None

    _state.evaluator = RagasEvaluator()

    tiered_info = f"tiered=fast:{llm_model_fast}/large:{llm_model}" if llm_model_fast else f"single:{llm_client.model_id}"
    logger.info(
        "Brain module ready. Registered fetchers: %s | expansion_factor=%.1f | top_n_before_rerank=%d"
        " | guardrails: min_rerank=%.3f max_same_src=%d low_conf=%.3f strict=%s judge=%s"
        " | query_rewrite=%s (max_variants=%d) | compression=%s | embedding_cache=%s"
        " | adaptive=%s fast_path=%s early_stop=%s | llm=%s | semantic_cache=%s (thresh=%.2f)",
        _state.registry.available(),
        _state.retrieval_expansion_factor,
        top_n_before_rerank,
        min_rerank_score,
        max_same_source,
        low_confidence_threshold,
        guardrail_strict_mode,
        enable_llm_judge,
        query_rewrite_enabled,
        query_rewrite_max_variants,
        compression_enabled,
        embedding_cache_enabled,
        _state.adaptive_pipeline_enabled,
        _state.fast_path_enabled,
        _state.early_stop_retrieval_enabled,
        tiered_info,
        semantic_cache_enabled,
        semantic_cache_threshold,
    )

    async def _warmup_models() -> None:
        """Warm up key model paths asynchronously so first user query is faster."""
        try:
            _ = _state.reranker._get_model()  # lazy-load cross encoder
        except Exception as exc:
            logger.warning("Reranker warmup failed: %s", exc)
        try:
            from ..router.intent_classifier import _compute_label_embeddings

            _compute_label_embeddings()
        except Exception as exc:
            logger.warning("Intent embedder warmup failed: %s", exc)
        try:
            fast_rag = _state.registry.get("fast_rag")
            if fast_rag is not None:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: fast_rag.fetch("warmup", top_k=1)
                )
        except Exception as exc:
            logger.warning("FastRAG warmup failed: %s", exc)

    if _env_bool("BRAIN_WARMUP_ENABLED", True):
        asyncio.create_task(_warmup_models())

    yield

    # Cleanup
    await _state.lightrag_client.aclose()


# --------------------------------------------------------------------------- #
# FastAPI app
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="Brain Module API",
    description="Multi-source Q&A reasoning and synthesis layer",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(audio_router)

# --------------------------------------------------------------------------- #
# Request / Response schemas
# --------------------------------------------------------------------------- #

class AskRequest(BaseModel):
    question: str
    top_k: int = 5
    use_cache: bool = True
    fetchers: list[str] | None = None   # override router if provided


class IngestRequest(BaseModel):
    records: list[dict[str, Any]]       # list of CanonicalQA-compatible dicts


class EvaluateRequest(BaseModel):
    question: str
    answer: str
    contexts: list[str]


# --- Frontend (Pebble / legacy ITRLM-shaped) compatibility ------------------

class LanguageDetectBody(BaseModel):
    text: str


class LanguageDetectionResponseModel(BaseModel):
    detected_language: str
    text: str


class TranslateBody(BaseModel):
    text: str
    source_lang: str
    target_lang: str


class TranslationResponseModel(BaseModel):
    translated_text: str
    source_lang: str
    target_lang: str


class GenerateAnswerRequest(BaseModel):
    question: str


class FrontendSource(BaseModel):
    title: str
    url: str
    domain: str
    has_external_link: bool
    citation_index: int | None = None
    retrieval_method: str | None = None
    score: float | None = None
    excerpt: str | None = None
    chunk_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerateAnswerResponseModel(BaseModel):
    question: str
    answer: str
    sources: list[FrontendSource] = Field(default_factory=list)
    trace_id: str | None = None
    trace_url: str | None = None
    latency_breakdown_ms: dict[str, float] | None = None
    retrieval_trace: list[dict[str, Any]] | None = None
    routing: dict[str, Any] | None = None
    from_cache: bool = False


def _brain_payload_to_frontend_sources(payload: dict[str, Any]) -> list[FrontendSource]:
    out: list[FrontendSource] = []
    for s in payload.get("sources") or []:
        url = (s.get("url") or "").strip()
        name = (s.get("source_name") or "source").strip()
        has_external_link = bool(url)
        domain = urlparse(url).netloc if has_external_link else (name or "local-source")
        out.append(
            FrontendSource(
                title=name or domain,
                url=url,
                domain=domain or "source",
                has_external_link=has_external_link,
                citation_index=s.get("citation_index"),
                retrieval_method=s.get("retrieval_method"),
                score=s.get("score"),
                excerpt=s.get("excerpt"),
                chunk_id=s.get("chunk_id"),
                metadata=s.get("metadata") or {},
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

async def _run_pipeline(req: AskRequest) -> tuple[BrainResponse, dict[str, Any]]:
    """Run the full brain pipeline and return (BrainResponse, response_dict)."""
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Route first on server side.
    route_t0 = time.perf_counter()
    plan = _state.router.route(req.question)
    active_fetchers = req.fetchers or plan.fetchers
    pipeline_mode = _compute_pipeline_mode(plan)
    is_fast_path = pipeline_mode == "fast"
    rewrite_cap = _state.fast_path_max_rewrite_variants if is_fast_path else None
    expansion_factor = (
        _state.fast_path_expansion_factor if is_fast_path else _state.retrieval_expansion_factor
    )
    timings["routing"] = (time.perf_counter() - route_t0) * 1000
    logger.info(
        "Query: %r | intent=%s | fetchers=%s | complexity=%.2f | mode=%s",
        req.question[:60],
        plan.intent.value,
        active_fetchers,
        plan.complexity_score,
        pipeline_mode,
    )

    # Fast path for non-CQA small-talk queries.
    # Chitchat is intentionally NOT cached.
    if plan.intent.value == "chitchat":
        response_dict = {
            "question": req.question,
            "answer": "Hello! I can help with CQA-style questions. Please ask a concrete question related to your knowledge base.",
            "answer_type": "unanswerable",
            "confidence": 1.0,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "model_used": "template",
            "reranker_used": "",
            "sources": [],
            "retrieval_trace": [],
            "error": None,
            "routing": {
                "intent": plan.intent.value,
                "complexity": plan.complexity_score,
                "reasoning": "Greeting/smalltalk detected; using instant template response.",
                "fetchers_used": [],
            },
        }
        timings["total"] = (time.perf_counter() - t0) * 1000
        response_dict["latency_breakdown_ms"] = {k: round(v, 2) for k, v in timings.items()}
        response_dict["from_cache"] = False
        trace_payload = {
            "timestamp": now_iso,
            "question": req.question,
            "from_cache": False,
            "routing": response_dict["routing"],
            "timings_ms": response_dict["latency_breakdown_ms"],
            "response": {
                "answer_type": response_dict["answer_type"],
                "confidence": response_dict["confidence"],
                "latency_ms": response_dict["latency_ms"],
                "sources_count": 0,
            },
        }
        trace_id, trace_url = _write_agentic_trace(trace_payload)
        if trace_id and trace_url:
            response_dict["trace_id"] = trace_id
            response_dict["trace_url"] = trace_url
        return None, response_dict  # type: ignore[return-value]

    # 1b. Set tiered LLM complexity (routes simple→fast model, complex→large)
    if isinstance(_state.synthesis_engine._llm, TieredLLMClient):
        _state.synthesis_engine._llm.set_complexity(plan.complexity_score)

    # 2. Cache check: exact match first, then semantic similarity
    cache_t0 = time.perf_counter()
    if req.use_cache:
        cached = await _state.cache.get(req.question)
        if cached is None and _state.semantic_cache is not None:
            cached = await _state.semantic_cache.get(req.question)
            if cached:
                cached["_cache_type"] = "semantic"
        timings["cache_lookup"] = (time.perf_counter() - cache_t0) * 1000
        if cached:
            cached["_from_cache"] = True
            timings["total"] = (time.perf_counter() - t0) * 1000
            cached["latency_breakdown_ms"] = {
                "cache_lookup": round(timings.get("cache_lookup", 0.0), 2),
                "total": round(timings["total"], 2),
            }
            cached["from_cache"] = True
            trace_payload = {
                "timestamp": now_iso,
                "question": req.question,
                "from_cache": True,
                "timings_ms": cached["latency_breakdown_ms"],
                "routing": cached.get("routing"),
                "retrieval_trace": cached.get("retrieval_trace", []),
                "response": {
                    "answer_type": cached.get("answer_type"),
                    "confidence": cached.get("confidence"),
                    "latency_ms": cached.get("latency_ms"),
                    "sources_count": len(cached.get("sources") or []),
                },
            }
            trace_id, trace_url = _write_agentic_trace(trace_payload)
            if trace_id and trace_url:
                cached["trace_id"] = trace_id
                cached["trace_url"] = trace_url
            return None, cached  # type: ignore[return-value]
    else:
        timings["cache_lookup"] = (time.perf_counter() - cache_t0) * 1000

    # 3. Query rewriting (expand into multiple variants for better recall)
    rewrite_t0 = time.perf_counter()
    query_variants = await _state.query_rewriter.rewrite(
        req.question, max_variants_override=rewrite_cap
    )
    timings["query_rewrite"] = (time.perf_counter() - rewrite_t0) * 1000
    if len(query_variants) > 1:
        logger.info("Query rewritten into %d variants: %s", len(query_variants), query_variants)

    # 4. Parallel fetch (across all query variants)
    fetch_t0 = time.perf_counter()
    fetch_top_k = int(req.top_k * expansion_factor)
    all_raw_chunks: list[dict] = []
    all_traces: list = []

    fetch_coros = [
        _state.parallel_fetcher.run(variant, active_fetchers, top_k=fetch_top_k)
        for variant in query_variants
    ]
    fetch_results = await asyncio.gather(*fetch_coros, return_exceptions=True)
    for i, result in enumerate(fetch_results):
        if isinstance(result, Exception):
            logger.warning("Fetch for variant %d failed: %s", i, result)
            continue
        chunks, traces = result
        all_raw_chunks.extend(chunks)
        if i == 0:
            all_traces.extend(traces)
    timings["parallel_fetch"] = (time.perf_counter() - fetch_t0) * 1000

    # 5. Aggregate + RRF
    agg_t0 = time.perf_counter()
    fused = _state.aggregator.aggregate(all_raw_chunks, fetcher_weights=plan.weights)
    timings["aggregate"] = (time.perf_counter() - agg_t0) * 1000

    # 6. Re-rank (can be skipped for low-complexity factual queries)
    rerank_t0 = time.perf_counter()
    retrieval_confidence = _compute_retrieval_confidence(fused)
    early_stop_applied = (
        _state.early_stop_retrieval_enabled
        and retrieval_confidence >= _state.early_stop_confidence_threshold
    )
    bypass_rerank = (
        (plan.intent.value == "factual" and plan.complexity_score <= _state.rerank_bypass_complexity_threshold)
        or (is_fast_path and _state.fast_path_skip_rerank)
        or early_stop_applied
    )
    if bypass_rerank:
        reranked = sorted(fused, key=lambda c: c.get("score", 0.0), reverse=True)[: req.top_k]
    else:
        reranked = _state.reranker.rerank(req.question, fused, top_k=req.top_k)
    timings["rerank"] = (time.perf_counter() - rerank_t0) * 1000

    # 7. Synthesise (includes context compression internally)
    synth_t0 = time.perf_counter()
    latency_ms = (time.perf_counter() - t0) * 1000
    response = await _state.synthesis_engine.synthesise(
        req.question,
        reranked,
        retrieval_traces=all_traces,
        answer_type=plan.intent,
        latency_ms=latency_ms,
        top_k_override=_state.fast_path_top_n_context if is_fast_path else None,
        max_tokens_override=_state.fast_path_max_synth_tokens if is_fast_path else None,
        enable_compression_override=not early_stop_applied,
    )
    timings["synthesis"] = (time.perf_counter() - synth_t0) * 1000
    timings["total"] = (time.perf_counter() - t0) * 1000

    response_dict = ResponseFormatter.to_dict(response)
    response_dict["routing"] = {
        "intent": plan.intent.value,
        "complexity": plan.complexity_score,
        "reasoning": plan.reasoning,
        "fetchers_used": active_fetchers,
        "pipeline_mode": pipeline_mode,
        "adaptive_pipeline_enabled": _state.adaptive_pipeline_enabled,
        "rerank_bypassed": bypass_rerank,
        "early_stop_applied": early_stop_applied,
        "retrieval_confidence": round(retrieval_confidence, 4),
    }
    response_dict["latency_breakdown_ms"] = {k: round(v, 2) for k, v in timings.items()}
    response_dict["from_cache"] = False

    # 9. Cache result (exact + semantic)
    if req.use_cache:
        await _state.cache.set(req.question, response_dict)
        if _state.semantic_cache is not None:
            await _state.semantic_cache.set(req.question, response_dict)

    trace_payload = {
        "timestamp": now_iso,
        "question": req.question,
        "from_cache": False,
        "routing": response_dict["routing"],
        "timings_ms": response_dict["latency_breakdown_ms"],
        "retrieval_trace": response_dict.get("retrieval_trace", []),
        "response": {
            "answer_type": response_dict.get("answer_type"),
            "confidence": response_dict.get("confidence"),
            "latency_ms": response_dict.get("latency_ms"),
            "sources_count": len(response_dict.get("sources") or []),
        },
    }
    trace_id, trace_url = _write_agentic_trace(trace_payload)
    if trace_id and trace_url:
        response_dict["trace_id"] = trace_id
        response_dict["trace_url"] = trace_url

    logger.info(
        "Pipeline latency [ms] cache=%.1f route=%.1f rewrite=%.1f fetch=%.1f agg=%.1f"
        " rerank=%.1f synth=%.1f total=%.1f",
        timings.get("cache_lookup", 0.0),
        timings.get("routing", 0.0),
        timings.get("query_rewrite", 0.0),
        timings.get("parallel_fetch", 0.0),
        timings.get("aggregate", 0.0),
        timings.get("rerank", 0.0),
        timings.get("synthesis", 0.0),
        timings.get("total", 0.0),
    )

    return response, response_dict


# --------------------------------------------------------------------------- #
# Pebble + multilingual helpers (used by frontend)
# --------------------------------------------------------------------------- #

@app.post("/detect-language", response_model=LanguageDetectionResponseModel)
async def detect_language_endpoint(body: LanguageDetectBody) -> LanguageDetectionResponseModel:
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text must not be empty")
    try:
        from langdetect import LangDetectException, detect
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="langdetect not installed") from exc
    try:
        code = detect(text)
    except LangDetectException:
        code = "en"
    return LanguageDetectionResponseModel(detected_language=code, text=body.text)


@app.post("/translate", response_model=TranslationResponseModel)
async def translate_endpoint(body: TranslateBody) -> TranslationResponseModel:
    if body.source_lang == body.target_lang:
        return TranslationResponseModel(
            translated_text=body.text,
            source_lang=body.source_lang,
            target_lang=body.target_lang,
        )
    llm = _state.synthesis_engine._llm
    messages = [
        {
            "role": "system",
            "content": (
                "You are a translation engine. Output only the translated text, "
                "with no quotes, labels, or explanation."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Translate from ISO 639-1 '{body.source_lang}' to '{body.target_lang}':\n\n"
                f"{body.text}"
            ),
        },
    ]
    translated, _ = await llm.complete(messages, max_tokens=2048, temperature=0.15)
    return TranslationResponseModel(
        translated_text=(translated or "").strip(),
        source_lang=body.source_lang,
        target_lang=body.target_lang,
    )


@app.post("/generate-answer", response_model=GenerateAnswerResponseModel)
async def generate_answer_endpoint(req: GenerateAnswerRequest) -> GenerateAnswerResponseModel:
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question must not be empty")
    try:
        _, response_dict = await _run_pipeline(AskRequest(question=q))
    except Exception as exc:
        logger.exception("Pipeline error for question: %s", q)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not response_dict:
        raise HTTPException(status_code=500, detail="empty pipeline response")
    return GenerateAnswerResponseModel(
        question=response_dict.get("question", q),
        answer=response_dict.get("answer", ""),
        sources=_brain_payload_to_frontend_sources(response_dict),
        trace_id=response_dict.get("trace_id"),
        trace_url=response_dict.get("trace_url"),
        latency_breakdown_ms=response_dict.get("latency_breakdown_ms"),
        retrieval_trace=response_dict.get("retrieval_trace"),
        routing=response_dict.get("routing"),
        from_cache=bool(response_dict.get("from_cache", False)),
    )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@app.get("/health")
async def health():
    lightrag_ok = await _state.lightrag_client.health()
    chunked_audio = simple_audio = False
    try:
        from audio.chunk import transcribe_chunked  # noqa: F401

        chunked_audio = True
    except ImportError:
        pass
    try:
        from audio.transcribe import transcribe_file  # noqa: F401

        simple_audio = True
    except ImportError:
        pass
    tts_ok = False
    try:
        import edge_tts  # noqa: F401
        tts_ok = True
    except ImportError:
        pass

    sc_stats = _state.semantic_cache.stats if _state.semantic_cache else {"enabled": False}
    llm_info = (
        {"type": "tiered", "fast": _state.synthesis_engine._llm.fast_model, "large": _state.synthesis_engine._llm.large_model}
        if isinstance(_state.synthesis_engine._llm, TieredLLMClient)
        else {"type": "single", "model": _state.synthesis_engine._llm.model_id}
    )

    return {
        "status": "ok",
        "fetchers": _state.registry.available(),
        "lightrag": "up" if lightrag_ok else "down",
        "audio": {
            "chunked_whisper": chunked_audio,
            "simple_whisper": simple_audio,
            "tts": tts_ok,
        },
        "llm": llm_info,
        "semantic_cache": sc_stats,
    }


@app.post("/ask")
async def ask(req: AskRequest) -> JSONResponse:
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    try:
        _, response_dict = await _run_pipeline(req)
    except Exception as exc:
        logger.exception("Pipeline error for question: %s", req.question)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(content=response_dict)


@app.post("/ask/stream")
async def ask_stream(req: AskRequest):
    """
    Server-Sent Events streaming endpoint with true token-level streaming.

    Emits:
      data: {"type": "routing", ...}
      data: {"type": "sources", ...}
      data: {"type": "token", "text": "..."}
      data: {"type": "done", "confidence": 0.87, "latency_ms": ...}
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    async def _stream() -> AsyncGenerator[str, None]:
        t0 = time.perf_counter()
        timings: dict[str, float] = {}

        # 0. Cache check (exact + semantic) for streaming path too.
        cache_t0 = time.perf_counter()
        cached: dict[str, Any] | None = None
        if req.use_cache:
            cached = await _state.cache.get(req.question)
            if cached is None and _state.semantic_cache is not None:
                cached = await _state.semantic_cache.get(req.question)
                if cached:
                    cached["_cache_type"] = "semantic"
        timings["cache_lookup"] = (time.perf_counter() - cache_t0) * 1000
        if cached:
            cached["from_cache"] = True
            timings["total"] = (time.perf_counter() - t0) * 1000
            latency = {
                "cache_lookup": round(timings.get("cache_lookup", 0.0), 2),
                "total": round(timings["total"], 2),
            }
            routing = cached.get("routing") or {}
            fetchers_used = routing.get("fetchers_used") or []
            if fetchers_used:
                yield _sse(
                    {
                        "type": "routing",
                        "intent": routing.get("intent", "unknown"),
                        "fetchers": fetchers_used,
                    }
                )
            cached_sources = cached.get("sources") or []
            if cached_sources:
                yield _sse({"type": "sources", "sources": cached_sources})
            yield _sse(
                {
                    "type": "done",
                    "answer": cached.get("answer", ""),
                    "confidence": cached.get("confidence", 0.0),
                    "latency_ms": round(timings["total"], 1),
                    "latency_breakdown_ms": latency,
                    "model_used": cached.get("model_used", ""),
                    "guardrail_flags": cached.get("guardrail_flags", []),
                    "from_cache": True,
                    "trace_url": cached.get("trace_url"),
                }
            )
            return

        # 1. Route
        route_t0 = time.perf_counter()
        plan = _state.router.route(req.question)
        active_fetchers = req.fetchers or plan.fetchers
        pipeline_mode = _compute_pipeline_mode(plan)
        is_fast_path = pipeline_mode == "fast"
        rewrite_cap = _state.fast_path_max_rewrite_variants if is_fast_path else None
        expansion_factor = (
            _state.fast_path_expansion_factor if is_fast_path else _state.retrieval_expansion_factor
        )
        timings["routing"] = (time.perf_counter() - route_t0) * 1000

        # 1b. Set tiered LLM complexity
        if isinstance(_state.synthesis_engine._llm, TieredLLMClient):
            _state.synthesis_engine._llm.set_complexity(plan.complexity_score)

        yield _sse({"type": "routing", "intent": plan.intent.value, "fetchers": active_fetchers})

        # 2. Query rewriting
        rewrite_t0 = time.perf_counter()
        query_variants = await _state.query_rewriter.rewrite(
            req.question, max_variants_override=rewrite_cap
        )
        timings["query_rewrite"] = (time.perf_counter() - rewrite_t0) * 1000

        # 3. Parallel fetch across all query variants + aggregate + rerank
        fetch_t0 = time.perf_counter()
        fetch_top_k = int(req.top_k * expansion_factor)
        all_raw_chunks: list[dict] = []

        fetch_coros = [
            _state.parallel_fetcher.run(variant, active_fetchers, top_k=fetch_top_k)
            for variant in query_variants
        ]
        fetch_results = await asyncio.gather(*fetch_coros, return_exceptions=True)
        for i, result in enumerate(fetch_results):
            if isinstance(result, Exception):
                logger.warning("Stream fetch for variant %d failed: %s", i, result)
                continue
            chunks, _ = result
            all_raw_chunks.extend(chunks)
        timings["parallel_fetch"] = (time.perf_counter() - fetch_t0) * 1000

        agg_t0 = time.perf_counter()
        fused = _state.aggregator.aggregate(all_raw_chunks, fetcher_weights=plan.weights)
        timings["aggregate"] = (time.perf_counter() - agg_t0) * 1000

        rerank_t0 = time.perf_counter()
        retrieval_confidence = _compute_retrieval_confidence(fused)
        early_stop_applied = (
            _state.early_stop_retrieval_enabled
            and retrieval_confidence >= _state.early_stop_confidence_threshold
        )
        bypass_rerank = (
            (plan.intent.value == "factual" and plan.complexity_score <= _state.rerank_bypass_complexity_threshold)
            or (is_fast_path and _state.fast_path_skip_rerank)
            or early_stop_applied
        )
        if bypass_rerank:
            reranked = sorted(fused, key=lambda c: c.get("score", 0.0), reverse=True)[: req.top_k]
        else:
            reranked = _state.reranker.rerank(req.question, fused, top_k=req.top_k)
        timings["rerank"] = (time.perf_counter() - rerank_t0) * 1000

        # 4. Context compression
        compress_t0 = time.perf_counter()
        if not early_stop_applied:
            reranked = _state.context_compressor.compress(req.question, reranked)
        timings["context_compression"] = (time.perf_counter() - compress_t0) * 1000

        # 5. Apply retrieval guardrails and build source cards
        from ..guardrails.retrieval_filter import cap_source_diversity, filter_low_relevance, filter_score_gap
        from ..guardrails.response_validator import validate_response
        from ..synthesis.citation_parser import validate_citations
        from ..synthesis.prompt_builder import build_synthesis_prompt

        synth_eng = _state.synthesis_engine
        top_k_budget = _state.fast_path_top_n_context if is_fast_path else synth_eng._top_k
        max_tokens_budget = _state.fast_path_max_synth_tokens if is_fast_path else 1024
        top_chunks = reranked[:top_k_budget]
        top_chunks = filter_low_relevance(
            top_chunks, min_score=synth_eng._min_rerank_score, min_keep=1
        )
        top_chunks = filter_score_gap(top_chunks, max_gap_ratio=0.5, min_keep=1)
        top_chunks = cap_source_diversity(
            top_chunks, max_per_source=synth_eng._max_same_source
        )

        source_cards = []
        for i, chunk in enumerate(top_chunks, start=1):
            sc = {
                "citation_index": i,
                "source_name": chunk.get("source", ""),
                "url": chunk.get("source_url", ""),
                "score": round(float(chunk.get("score", 0.0)), 4),
                "excerpt": chunk.get("text", "")[:300],
                "retrieval_method": chunk.get("retrieval_method", ""),
                "chunk_id": chunk.get("chunk_id", ""),
            }
            source_cards.append(sc)
        yield _sse({"type": "sources", "sources": source_cards})

        # 6. Stream LLM tokens (with confidence hint in prompt)
        avg_score = (
            sum(s["score"] for s in source_cards) / max(len(source_cards), 1)
        )

        source_blocks = [
            {
                "citation_index": s["citation_index"],
                "source_name": s["source_name"],
                "excerpt": top_chunks[s["citation_index"] - 1].get("text", "")[:600],
                "score": s["score"],
            }
            for s in source_cards
        ]
        messages = build_synthesis_prompt(
            req.question,
            source_blocks,
            answer_type_hint=plan.intent.value,
            confidence_hint=avg_score < synth_eng._low_confidence_threshold,
        )

        llm = synth_eng._llm
        full_answer = ""
        synth_t0 = time.perf_counter()
        try:
            async for token in llm.stream(messages, max_tokens=max_tokens_budget, temperature=0.2):
                full_answer += token
                yield _sse({"type": "token", "text": token})
        except Exception as exc:
            logger.error("LLM stream error: %s", exc)
            yield _sse({"type": "error", "message": str(exc)})
            return

        timings["synthesis"] = (time.perf_counter() - synth_t0) * 1000

        # 7. Post-stream guardrails (citation cleanup + response validation)
        from ..response.schema import SourceCard as _SC
        _sc_objs = [
            _SC(
                source_name=s["source_name"],
                excerpt=s["excerpt"],
                url=s["url"],
                score=s["score"],
                retrieval_method=s["retrieval_method"],
                chunk_id=s["chunk_id"],
                citation_index=s["citation_index"],
            )
            for s in source_cards
        ]
        cleaned_answer, invalid_refs = validate_citations(full_answer, _sc_objs)
        if invalid_refs:
            logger.warning("Stream: LLM cited non-existent source indices: %s", invalid_refs)

        validation = validate_response(
            req.question,
            cleaned_answer,
            avg_rerank_score=avg_score,
            answer_type=plan.intent.value,
            low_confidence_threshold=synth_eng._low_confidence_threshold,
            strict_mode=synth_eng._guardrail_strict_mode,
        )
        guardrail_flags = validation.issues
        final_answer = validation.modified_answer if validation.modified_answer else cleaned_answer

        timings["total"] = (time.perf_counter() - t0) * 1000
        latency_breakdown = {k: round(v, 2) for k, v in timings.items()}

        # 8. Cache streamed response so repeated identical queries hit fast path.
        if req.use_cache:
            cache_payload: dict[str, Any] = {
                "question": req.question,
                "answer": final_answer,
                "sources": source_cards,
                "confidence": round(avg_score, 4),
                "answer_type": plan.intent.value,
                "latency_ms": round(timings["total"], 1),
                "model_used": llm.model_id,
                "reranker_used": _state.reranker.model_name,
                "retrieval_trace": [],
                "guardrail_flags": guardrail_flags,
                "routing": {
                    "intent": plan.intent.value,
                    "complexity": plan.complexity_score,
                    "reasoning": plan.reasoning,
                    "fetchers_used": active_fetchers,
                    "pipeline_mode": pipeline_mode,
                    "adaptive_pipeline_enabled": _state.adaptive_pipeline_enabled,
                    "rerank_bypassed": bypass_rerank,
                    "early_stop_applied": early_stop_applied,
                    "retrieval_confidence": round(retrieval_confidence, 4),
                },
                "latency_breakdown_ms": latency_breakdown,
                "from_cache": False,
            }
            await _state.cache.set(req.question, cache_payload)
            if _state.semantic_cache is not None:
                await _state.semantic_cache.set(req.question, cache_payload)

        yield _sse({
            "type": "done",
            "answer": final_answer,
            "confidence": round(avg_score, 4),
            "latency_ms": round(timings["total"], 1),
            "latency_breakdown_ms": latency_breakdown,
            "model_used": llm.model_id,
            "guardrail_flags": guardrail_flags,
            "pipeline_mode": pipeline_mode,
            "early_stop_applied": early_stop_applied,
            "from_cache": False,
        })

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.post("/evaluate")
async def evaluate(req: EvaluateRequest):
    """Run Ragas evaluation on a question/answer/context triple."""
    from ..response.schema import SourceCard, BrainResponse, AnswerType

    fake_response = BrainResponse(
        question=req.question,
        answer=req.answer,
        sources=[
            SourceCard(
                source_name=f"ctx_{i}",
                excerpt=ctx,
                url="",
                score=0.5,
                retrieval_method="manual",
                citation_index=i + 1,
            )
            for i, ctx in enumerate(req.contexts)
        ],
        confidence=0.5,
        answer_type=AnswerType.UNKNOWN,
    )
    scores = await _state.evaluator.evaluate_one(fake_response)
    return {"scores": scores}


@app.post("/ingest/lightrag")
async def ingest_lightrag(req: IngestRequest):
    """
    Ingest CanonicalQA-compatible JSON records into the LightRAG server.
    """
    if not await _state.lightrag_client.health():
        raise HTTPException(status_code=503, detail="LightRAG server is not available")

    adapter = LightRAGIngestionAdapter(_state.lightrag_client)
    results = await adapter.ingest_batch(req.records, batch_size=20)
    errors = [r for r in results if "error" in r]
    return {
        "ingested": len(results) - len(errors),
        "errors": len(errors),
    }


@app.get("/sources")
async def list_sources():
    return {"fetchers": _state.registry.available()}


@app.get("/traces/{trace_id}")
async def download_trace(trace_id: str):
    if not trace_id or "/" in trace_id or ".." in trace_id:
        raise HTTPException(status_code=400, detail="invalid trace id")
    trace_path = _state.trace_dir / f"{trace_id}.json"
    if not trace_path.exists():
        raise HTTPException(status_code=404, detail="trace not found")
    return FileResponse(
        path=trace_path,
        media_type="application/json",
        filename=f"brain-trace-{trace_id}.json",
    )


# --------------------------------------------------------------------------- #
# SSE helper
# --------------------------------------------------------------------------- #

def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
