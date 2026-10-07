// src/App.tsx
import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sidebar } from "./components/Sidebar";
import { PromptBar } from "./components/PromptBar";
import { ChatThread } from "./components/ChatThread";
import { useSpeech } from "./hooks/useSpeech";
import { useUiMode } from "./contexts/UiModeContext";
import { API_BASE_URL, DEV_MOCK_API } from "./config";
import { buildMockGenerateAnswerResponse } from "./devMockPayload";
import "./App.css";

const ASSISTANT_TAGLINE =
  "Multi-source Q&A over open corpora — answers with citations you can verify";

const HERO_SUGGESTIONS = [
  { label: "What is retrieval-augmented generation?", prompt: "What is retrieval-augmented generation?" },
  { label: "How does binary search work?", prompt: "How does binary search work?" },
  { label: "What is multi-hop question answering?", prompt: "What is multi-hop question answering?" },
];

export interface Source {
  title: string;
  url: string;
  domain: string;
  has_external_link?: boolean;
  citation_index?: number | null;
  retrieval_method?: string | null;
  score?: number | null;
  excerpt?: string | null;
  chunk_id?: string | null;
  /** e.g. `source_kind: "wikipedia" | "arxiv" | "internal_index"` — drives source icons (`lib/dataSourceType.ts`). */
  metadata?: Record<string, unknown>;
}

export interface Message {
  id: string;
  sender: "user" | "pebble";
  text: string;
  mode?: "speech" | "text";
  lang?: string;
  /** Indicates a non-English answer is still being prepared behind the scenes. */
  phase?: "streaming" | "translating";
  sources?: Source[];
  traceUrl?: string;
  latencyBreakdownMs?: Record<string, number>;
  retrievalTrace?: Array<{
    fetcher: string;
    latency_ms: number;
    results_returned: number;
    error?: string | null;
  }>;
  routing?: Record<string, unknown>;
  fromCache?: boolean;
  timestamp: number;
}

interface LanguageDetectionResponse {
  detected_language: string;
  text: string;
}

interface TranslationResponse {
  translated_text: string;
  source_lang: string;
  target_lang: string;
}

interface GenerateAnswerResponse {
  question: string;
  answer: string;
  sources?: Source[];
  trace_url?: string;
  latency_breakdown_ms?: Record<string, number>;
  retrieval_trace?: Array<{
    fetcher: string;
    latency_ms: number;
    results_returned: number;
    error?: string | null;
  }>;
  routing?: Record<string, unknown>;
  from_cache?: boolean;
}

export default function App() {
  const { devMode } = useUiMode();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [activeLanguage, setActiveLanguage] = useState<string | null>(null);
  const [autoSpeak, setAutoSpeak] = useState(false);
  const { speakText, stopSpeaking, isSpeakable, isSpeaking } = useSpeech();

  const hasConversation = messages.length > 0 || isProcessing;

  const handleSend = async (
    text: string,
    mode: "speech" | "text",
    meta?: { detectedLanguage?: string; englishQuery?: string }
  ) => {
    const trimmed = text.trim();
    if (!trimmed || isProcessing) return;

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      sender: "user",
      text: trimmed,
      mode,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsProcessing(true);

    try {
      const detectStart = performance.now();
      const languageCode =
        meta?.detectedLanguage ??
        (DEV_MOCK_API ? "en" : await detectLanguageFromAPI(trimmed));
      const detectMs = performance.now() - detectStart;
      setActiveLanguage(languageCode);

      const preTranslateStart = performance.now();
      const englishQuestion =
        meta?.englishQuery?.trim() ||
        (DEV_MOCK_API
          ? trimmed
          : await translateText(trimmed, languageCode, "en"));
      const preTranslateMs = performance.now() - preTranslateStart;

      const answerStart = performance.now();
      if (DEV_MOCK_API) {
        const mockDelayMs = 900 + Math.floor(Math.random() * 500);
        await new Promise((resolve) => window.setTimeout(resolve, mockDelayMs));
        const pushId = Date.now();
        const answerData = buildMockGenerateAnswerResponse(englishQuestion, pushId);
        const answerMs = performance.now() - answerStart;
        console.info("[VITE_DEV_MOCK_API] mock generate-answer", { pushId, question: englishQuestion });

        const postTranslateStart = performance.now();
        const finalAnswer = answerData.answer;
        const postTranslateMs = performance.now() - postTranslateStart;

        console.info("frontend_latency_ms", {
          detect_language: Number(detectMs.toFixed(1)),
          translate_to_english: Number(preTranslateMs.toFixed(1)),
          backend_generate_answer: Number(answerMs.toFixed(1)),
          translate_to_user_language: Number(postTranslateMs.toFixed(1)),
        });

        setMessages((prev) => [
          ...prev,
          {
            id: `p-${Date.now()}`,
            sender: "pebble",
            text: finalAnswer,
            lang: languageCode,
            sources: answerData.sources ?? defaultSources,
            traceUrl: answerData.trace_url
              ? `${API_BASE_URL}${answerData.trace_url}`
              : undefined,
            latencyBreakdownMs: answerData.latency_breakdown_ms ?? {},
            retrievalTrace: answerData.retrieval_trace ?? [],
            routing: answerData.routing ?? {},
            fromCache: Boolean(answerData.from_cache),
            timestamp: Date.now(),
          },
        ]);
      } else {
        // True SSE streaming from /ask/stream
        const msgId = `p-${Date.now()}`;

        const needsTranslation = languageCode !== "en";

        // Insert an empty assistant message we'll progressively fill
        setMessages((prev) => [
          ...prev,
          {
            id: msgId,
            sender: "pebble",
            text: "",
            lang: languageCode,
            phase: needsTranslation ? "streaming" : undefined,
            timestamp: Date.now(),
          },
        ]);

        const sseResponse = await fetch(`${API_BASE_URL}/ask/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: englishQuestion }),
        });
        if (!sseResponse.ok || !sseResponse.body) throw new Error("Stream request failed");

        const reader = sseResponse.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let streamedAnswer = "";
        let streamSources: Source[] = [];
        let streamLatency: Record<string, number> = {};
        let streamRouting: Record<string, unknown> = {};
        let streamFromCache = false;
        let streamTraceUrl: string | undefined;

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const jsonStr = line.slice(6).trim();
            if (!jsonStr) continue;
            try {
              const evt = JSON.parse(jsonStr);

              if (evt.type === "routing") {
                streamRouting = { intent: evt.intent, fetchers: evt.fetchers };
              } else if (evt.type === "sources") {
                streamSources = (evt.sources ?? []).map((s: Record<string, unknown>, i: number) => ({
                  title: (s.source_name as string) || `Source ${i + 1}`,
                  url: (s.url as string) || "",
                  domain: (s.url as string) ? new URL(s.url as string).hostname : "local-source",
                  has_external_link: Boolean(s.url),
                  citation_index: s.citation_index as number,
                  score: s.score as number,
                  excerpt: (s.excerpt as string) ?? "",
                  retrieval_method: (s.retrieval_method as string) ?? "",
                  chunk_id: (s.chunk_id as string) ?? "",
                  metadata: {},
                }));
                setMessages((prev) =>
                  prev.map((m) => (m.id === msgId ? { ...m, sources: streamSources, routing: streamRouting } : m))
                );
              } else if (evt.type === "token") {
                streamedAnswer += evt.text;
                if (!needsTranslation) {
                  const captured = streamedAnswer;
                  setMessages((prev) =>
                    prev.map((m) => (m.id === msgId ? { ...m, text: captured } : m))
                  );
                }
              } else if (evt.type === "done") {
                streamLatency = evt.latency_breakdown_ms ?? {};
                streamFromCache = Boolean(evt.from_cache);
                streamTraceUrl = typeof evt.trace_url === "string"
                  ? (evt.trace_url.startsWith("http") ? evt.trace_url : `${API_BASE_URL}${evt.trace_url}`)
                  : undefined;
                const finalText = evt.answer || streamedAnswer;

                let translated: string;
                if (needsTranslation) {
                  setMessages((prev) =>
                    prev.map((m) => (m.id === msgId ? { ...m, phase: "translating" } : m))
                  );
                  const postTranslateStart2 = performance.now();
                  translated = await translateText(finalText, "en", languageCode);
                  const postTranslateMs2 = performance.now() - postTranslateStart2;
                  const answerMs2 = performance.now() - answerStart;
                  console.info("frontend_latency_ms", {
                    detect_language: Number(detectMs.toFixed(1)),
                    translate_to_english: Number(preTranslateMs.toFixed(1)),
                    backend_stream_answer: Number(answerMs2.toFixed(1)),
                    translate_to_user_language: Number(postTranslateMs2.toFixed(1)),
                  });
                } else {
                  translated = finalText;
                  const answerMs2 = performance.now() - answerStart;
                  console.info("frontend_latency_ms", {
                    detect_language: Number(detectMs.toFixed(1)),
                    translate_to_english: Number(preTranslateMs.toFixed(1)),
                    backend_stream_answer: Number(answerMs2.toFixed(1)),
                  });
                }

                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === msgId
                      ? {
                          ...m,
                          text: translated,
                          lang: languageCode,
                          phase: undefined,
                          sources: streamSources.length ? streamSources : defaultSources,
                          latencyBreakdownMs: streamLatency,
                          routing: streamRouting,
                          fromCache: streamFromCache,
                          traceUrl: streamTraceUrl,
                        }
                      : m
                  )
                );
              } else if (evt.type === "error") {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === msgId ? { ...m, text: `Error: ${evt.message}` } : m
                  )
                );
              }
            } catch {
              // malformed SSE line; skip
            }
          }
        }
      }

      if (autoSpeak && isSpeakable) {
        const lastMsg = messages[messages.length - 1];
        if (lastMsg?.sender === "pebble" && lastMsg.text) speakText(lastMsg.text, lastMsg.lang);
      }
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          id: `p-err-${Date.now()}`,
          sender: "pebble",
          text: "Couldn’t reach the brain API. Check that the server is running and try again.",
          timestamp: Date.now(),
        },
      ]);
    } finally {
      setActiveLanguage(null);
      setIsProcessing(false);
    }
  };

  const handleQuickPrompt = (text: string) => {
    void handleSend(text, "text");
  };

  return (
    <div className="app-root">
      <Sidebar />

      <main className="workspace">
        <header className="workspace__header">
          <div className="brand">
            <div className="brand__mark">P</div>
            <div className="brand__text">
              <div className="brand__name">Pebble</div>
              <div className="brand__tagline">{ASSISTANT_TAGLINE}</div>
            </div>
            {devMode && (
              <>
                <div className="brand__divider" />
                <div className="brand__tag">dev.console / v2.4.0</div>
              </>
            )}
          </div>

          <div className="header__status">
            {devMode && DEV_MOCK_API && (
              <span className="dev-mock-pill" title="VITE_DEV_MOCK_API is on — no real API calls">
                dev :: mock api
              </span>
            )}
            <button
              type="button"
              className={`speak-toggle ${!isSpeakable ? "speak-toggle--disabled" : ""} ${
                autoSpeak ? "speak-toggle--on" : ""
              }`}
              onClick={() => setAutoSpeak((prev) => !prev)}
              disabled={!isSpeakable}
              title={isSpeakable ? "Read answers aloud automatically" : "Speech not supported in this browser"}
            >
              <span className={`speak-toggle__dot ${isSpeaking ? "speak-toggle__dot--active" : ""}`} />
              {devMode
                ? isSpeakable
                  ? autoSpeak
                    ? "ifSpeakable :: on"
                    : "ifSpeakable :: off"
                  : "ifSpeakable :: unavailable"
                : isSpeakable
                  ? autoSpeak
                    ? "Auto-read on"
                    : "Auto-read off"
                  : "Read-aloud unavailable"}
            </button>
            {devMode && activeLanguage ? (
              <motion.div
                className="lang-pill"
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <span className="lang-pill__dot" />
                lang :: <strong>{activeLanguage.toUpperCase()}</strong>
              </motion.div>
            ) : devMode ? (
              <div className="header__status-item">
                <span className="header__status-dot" />
                brain API :: online
              </div>
            ) : (
              <div className="header__status-item header__status-item--subtle">
                <span className="header__status-dot" />
                Online
              </div>
            )}
          </div>
        </header>

        <div className={`stage${hasConversation ? " stage--active" : ""}`}>
          <div className="stage__viewport">
            <AnimatePresence>
              {!hasConversation && (
                <motion.section
                  key="hero"
                  className="hero"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, transition: { duration: 0.2, ease: "easeOut" } }}
                  transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                >
                {devMode && <div className="hero__eyebrow">multi-source CQA · research demo</div>}
                <h1 className="hero__title">
                  {devMode ? (
                    <>
                      Query the CanonicalQA index.
                      <span className="hero__title-accent">Routed RAG + attributed synthesis.</span>
                    </>
                  ) : (
                    <>
                      Ask across open Q&A sources.
                      <span className="hero__title-accent">Answers with sources, not guesswork.</span>
                    </>
                  )}
                </h1>
                <p className="hero__sub">
                  {devMode
                    ? "This UI talks to the brain module: query routing, parallel fetchers (dense / hybrid / graph), fusion, re-rank, and cited answers over heterogeneous corpora normalized into one schema."
                    : "Your question is routed through retrieval and synthesis over Wikipedia-style and community Q&A data. Every reply lists passages you can open and check."}
                </p>
                {!devMode && (
                  <div className="hero__try">
                    <p className="hero__try-label">Try asking</p>
                    <ul className="hero__try-list">
                      {HERO_SUGGESTIONS.map((s) => (
                        <li key={s.label}>
                          <button
                            type="button"
                            className="hero__try-chip"
                            onClick={() => handleQuickPrompt(s.prompt)}
                          >
                            {s.label}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="hero__specs">
                  <span>voice input</span>
                  <span>multilingual query</span>
                  <span>attributed citations</span>
                </div>
                </motion.section>
              )}
            </AnimatePresence>

            <AnimatePresence>
              {hasConversation && (
                <ChatThread
                  key="thread"
                  messages={messages}
                  isProcessing={isProcessing}
                  onQuickPrompt={handleQuickPrompt}
                  onSpeakMessage={speakText}
                  onStopSpeaking={stopSpeaking}
                  isSpeakable={isSpeakable}
                  isSpeaking={isSpeaking}
                />
              )}
            </AnimatePresence>
          </div>

          <div
            className={`prompt-dock ${hasConversation ? "prompt-dock--bottom" : "prompt-dock--center"}`}
          >
            <PromptBar onSubmit={handleSend} disabled={isProcessing} />
            <p className="prompt-dock__legal">
              {devMode
                ? "models can hallucinate :: always verify against cited passages"
                : "Language models can be wrong. Use the cited sources to verify."}
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

const defaultSources: Source[] = [
  {
    title: "Wikipedia — Retrieval-augmented generation",
    url: "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
    domain: "wikipedia.org",
    has_external_link: true,
    metadata: {},
  },
  {
    title: "Stack Overflow — referencing material",
    url: "https://stackoverflow.com/help/referencing",
    domain: "stackoverflow.com",
    has_external_link: true,
    metadata: {},
  },
];

async function translateText(
  text: string,
  sourceLang: string,
  targetLang: string
): Promise<string> {
  if (sourceLang === targetLang) return text;
  const response = await fetch(`${API_BASE_URL}/translate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      source_lang: sourceLang,
      target_lang: targetLang,
    }),
  });
  if (!response.ok) throw new Error("Translation failed");
  const data: TranslationResponse = await response.json();
  return data.translated_text;
}

async function detectLanguageFromAPI(text: string): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/detect-language`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) throw new Error("Failed to detect language");
  const data: LanguageDetectionResponse = await response.json();
  return data.detected_language;
}