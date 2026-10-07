/**
 * Temporary dev-only payload for frontend work without brain_module running.
 * Enable with VITE_DEV_MOCK_API=true (see config.ts).
 * `pushId` changes on every user submit so dev mode can verify fresh data.
 */

/** Mirrors `Source` in App.tsx (kept separate to avoid circular imports). */
export interface MockSourcePayload {
  title: string;
  url: string;
  domain: string;
  has_external_link?: boolean;
  citation_index?: number | null;
  retrieval_method?: string | null;
  score?: number | null;
  excerpt?: string | null;
  chunk_id?: string | null;
  metadata?: Record<string, unknown>;
}

export interface MockGenerateAnswerShape {
  question: string;
  answer: string;
  sources: MockSourcePayload[];
  trace_url?: string;
  latency_breakdown_ms: Record<string, number>;
  retrieval_trace: Array<{
    fetcher: string;
    latency_ms: number;
    results_returned: number;
    error?: string | null;
  }>;
  routing: Record<string, unknown>;
  from_cache: boolean;
}

const CHITCHAT =
  /^\s*(hi|hello|hey|yo|hola|namaste|good (morning|afternoon|evening)|how are you|how's it going|what's up|sup|thanks|thank you|thx)\s*[!.?]*\s*$/i;

export function buildMockGenerateAnswerResponse(
  question: string,
  pushId: number
): MockGenerateAnswerShape {
  const sources: MockSourcePayload[] = [
    {
      title: "Retrieval-augmented generation",
      url: "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
      domain: "wikipedia.org",
      has_external_link: true,
      citation_index: 1,
      retrieval_method: "fast_rag",
      score: 0.91,
      excerpt:
        "Retrieval-augmented generation is a technique that grants large language models access to external information retrieval systems.",
      chunk_id: `mock-chunk-${pushId}-1`,
      metadata: { mock: true, pushId, source_kind: "wikipedia" },
    },
    {
      title: "Canonical QA row — Stack Exchange archive",
      url: "",
      domain: "stackexchange.com",
      has_external_link: false,
      citation_index: 2,
      retrieval_method: "fast_rag",
      score: 0.72,
      excerpt:
        "Mock passage from the unified CanonicalQA index (community Q&A normalized with Wikipedia-style records).",
      chunk_id: `mock-chunk-${pushId}-2`,
      metadata: {
        mock: true,
        pushId,
        source_file: "canonical_qa.parquet",
        verified_internal: true,
      },
    },
    {
      title: "Attention Is All You Need",
      url: "https://arxiv.org/abs/1706.03762",
      domain: "arxiv.org",
      has_external_link: true,
      citation_index: 3,
      retrieval_method: "hybrid_dense_sparse",
      score: 0.68,
      excerpt: "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
      chunk_id: `mock-chunk-${pushId}-3`,
      metadata: { mock: true, pushId, source_kind: "arxiv" },
    },
    {
      title: "pebble / brain_module — README",
      url: "https://github.com/example/pebble-brain",
      domain: "github.com",
      has_external_link: true,
      citation_index: 4,
      retrieval_method: "graph_augmented",
      score: 0.55,
      excerpt: "Mock hit from a public code repository (domain match shows the GitHub mark in the UI).",
      chunk_id: `mock-chunk-${pushId}-4`,
      metadata: { mock: true, pushId, source_kind: "github" },
    },
    {
      title: "SQuAD v2.0 — sample passage",
      url: "",
      domain: "squad.dataset",
      has_external_link: false,
      citation_index: 5,
      retrieval_method: "fast_rag",
      score: 0.61,
      excerpt: "Mock row from a reading-comprehension style corpus (metadata-driven icon).",
      chunk_id: `mock-chunk-${pushId}-5`,
      metadata: {
        mock: true,
        pushId,
        source_kind: "reading_comprehension",
        verified_internal: true,
      },
    },
  ];

  const greetingAnswer = `Hi! I'm Pebble — the chat UI for this personal **multi-source CQA** project.

Ask factual or technical questions. Answers are meant to be **grounded in retrieved passages** from open corpora (Wikipedia, Stack Exchange, reading-comprehension sets, etc.) that all map to one **CanonicalQA** schema.

Open the sources under each reply to see what the model was allowed to use.`;

  const factualAnswer = `**Retrieval-augmented generation (RAG)** is a pattern where a model answers only after **fetching** relevant text from a corpus (vector DB, hybrid search, or graph-augmented retrieval). That grounds the answer in real documents instead of pure parametric memory.

This codebase’s **brain** layer routes your query, runs one or more fetchers in parallel, fuses and re-ranks hits, then synthesizes a reply with **per-source attribution** — the same idea as in multi-source QA research.

Turn on **Dev mode** (wrench in the sidebar) to inspect mock timings and routing metadata while you build the UI.`;

  const answer = CHITCHAT.test(question) ? greetingAnswer : factualAnswer;

  return {
    question,
    answer,
    sources,
    trace_url: undefined,
    latency_breakdown_ms: {
      mock_push_id: pushId,
      cache_lookup: 0.5,
      routing: 0.2,
      parallel_fetch: 12.3,
      aggregate: 1.1,
      rerank: 4.4,
      synthesis: 8.8,
      total: 27.3,
    },
    retrieval_trace: [
      {
        fetcher: "fast_rag",
        latency_ms: 11.2,
        results_returned: 10,
        error: null,
      },
    ],
    routing: {
      intent: "factual",
      complexity: 0.12,
      reasoning: "Mock routing — enable Dev mode in the sidebar to inspect",
      fetchers_used: ["fast_rag"],
      rerank_bypassed: false,
      mock: true,
      pushId,
    },
    from_cache: false,
  };
}
