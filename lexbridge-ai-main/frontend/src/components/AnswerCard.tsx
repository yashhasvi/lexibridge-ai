// src/components/AnswerCard.tsx
import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import type { Message, Source } from "../App";
import { useUiMode } from "../contexts/UiModeContext";
import { SourceIcon } from "./SourceIcon";

interface AnswerCardProps {
  message: Message;
  previousUserText?: string;
  onQuickPrompt?: (text: string) => void;
  onSpeak: (text: string, lang?: string) => void;
  onStop: () => void;
  isSpeakable: boolean;
  isSpeaking: boolean;
}

interface Block {
  type: "text" | "code";
  content: string;
  lang?: string;
}

const CHITCHAT_PATTERN =
  /^\s*(hi|hello|hey|yo|hola|namaste|good (morning|afternoon|evening)|how are you|how's it going|what's up|sup|thanks|thank you|thx)\s*[!.?]*\s*$/i;

const GREETING_SUGGESTIONS = [
  { label: "What is RAG?", prompt: "What is retrieval-augmented generation?" },
  { label: "Binary search", prompt: "How does binary search work?" },
  { label: "Multi-hop QA", prompt: "What is multi-hop question answering?" },
];

const FOLLOW_UPS = [
  { label: "Supporting passages", prompt: "Which retrieved passages support your answer most directly?" },
  { label: "Simpler explanation", prompt: "Can you explain that in simpler terms?" },
  { label: "Go deeper", prompt: "What should I read next to go deeper on this topic?" },
];

const parseAnswer = (text: string): Block[] => {
  const blocks: Block[] = [];
  const regex = /```(\w+)?\n?([\s\S]*?)```/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) {
      blocks.push({ type: "text", content: text.slice(last, m.index).trim() });
    }
    blocks.push({ type: "code", lang: m[1] || "text", content: m[2].trim() });
    last = regex.lastIndex;
  }
  if (last < text.length) {
    blocks.push({ type: "text", content: text.slice(last).trim() });
  }
  if (blocks.length === 0) blocks.push({ type: "text", content: text });
  return blocks.filter((b) => b.content.length > 0);
};

const KEYWORDS = new Set([
  "const", "let", "var", "function", "return", "if", "else", "for", "while", "class",
  "extends", "new", "this", "import", "from", "export", "default", "async", "await",
  "try", "catch", "finally", "throw", "typeof", "instanceof", "in", "of", "true",
  "false", "null", "undefined", "def", "lambda", "pass", "None", "True", "False",
  "self", "print", "public", "private", "static", "void", "int", "string", "bool",
  "interface", "type", "enum", "struct", "impl", "fn", "match", "pub", "use", "mut",
]);

const escape = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const highlight = (code: string): string => {
  const out: string[] = [];
  let i = 0;
  const n = code.length;

  while (i < n) {
    const ch = code[i];

    if (ch === "/" && code[i + 1] === "/") {
      let j = i;
      while (j < n && code[j] !== "\n") j++;
      out.push(`<span class="tok-c">${escape(code.slice(i, j))}</span>`);
      i = j;
      continue;
    }
    if (ch === "#") {
      let j = i;
      while (j < n && code[j] !== "\n") j++;
      out.push(`<span class="tok-c">${escape(code.slice(i, j))}</span>`);
      i = j;
      continue;
    }
    if (ch === "/" && code[i + 1] === "*") {
      const j = code.indexOf("*/", i + 2);
      const end = j === -1 ? n : j + 2;
      out.push(`<span class="tok-c">${escape(code.slice(i, end))}</span>`);
      i = end;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      const quote = ch;
      let j = i + 1;
      while (j < n) {
        if (code[j] === "\\") {
          j += 2;
          continue;
        }
        if (code[j] === quote) {
          j++;
          break;
        }
        j++;
      }
      out.push(`<span class="tok-s">${escape(code.slice(i, j))}</span>`);
      i = j;
      continue;
    }
    if (/[0-9]/.test(ch)) {
      let j = i;
      while (j < n && /[0-9_.xXa-fA-F]/.test(code[j])) j++;
      out.push(`<span class="tok-n">${escape(code.slice(i, j))}</span>`);
      i = j;
      continue;
    }
    if (/[A-Za-z_$]/.test(ch)) {
      let j = i;
      while (j < n && /[A-Za-z0-9_$]/.test(code[j])) j++;
      const word = code.slice(i, j);
      if (KEYWORDS.has(word)) {
        out.push(`<span class="tok-k">${escape(word)}</span>`);
      } else if (code[j] === "(") {
        out.push(`<span class="tok-f">${escape(word)}</span>`);
      } else {
        out.push(escape(word));
      }
      i = j;
      continue;
    }
    out.push(escape(ch));
    i++;
  }
  return out.join("");
};

function isVerifiedInternal(s: Source): boolean {
  if (s.has_external_link && s.url) return false;
  const meta = s.metadata as Record<string, unknown> | undefined;
  if (meta?.verified_internal === true) return true;
  return Boolean(!s.url && s.has_external_link === false);
}

function sourceSubtitle(s: Source): string {
  if (isVerifiedInternal(s)) return "Verified internal source";
  if (s.domain) return s.domain;
  return "Reference";
}

export const AnswerCard: React.FC<AnswerCardProps> = ({
  message,
  previousUserText,
  onQuickPrompt,
  onSpeak,
  onStop,
  isSpeakable,
  isSpeaking,
}) => {
  const { devMode } = useUiMode();
  const blocks = useMemo(() => parseAnswer(message.text), [message.text]);

  const [selectedSource, setSelectedSource] = useState<Source | null>(null);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);

  const sources = message.sources ?? [];
  const trustedCount = sources.length;
  const showGreetingChips =
    Boolean(previousUserText && CHITCHAT_PATTERN.test(previousUserText)) && Boolean(onQuickPrompt);

  return (
    <motion.article
      className="answer"
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    >
      <header className="answer__header">
        <div className="answer__avatar" aria-hidden>
          P
        </div>
        <div className="answer__identity">
          <div className="answer__name">Pebble</div>
          {devMode && (
            <div className="answer__role">research synthesis</div>
          )}
        </div>
        <div className="answer__audio-actions">
          <button
            type="button"
            className="answer__audio-btn"
            disabled={!isSpeakable}
            onClick={() => onSpeak(message.text, message.lang)}
            title={isSpeakable ? "Listen to this answer" : "Speech not supported"}
          >
            {devMode ? "Listen" : "Play"}
          </button>
          <button
            type="button"
            className="answer__audio-btn"
            disabled={!isSpeakable || !isSpeaking}
            onClick={onStop}
            title="Stop"
          >
            Stop
          </button>
        </div>
        {devMode && <div className="answer__tag">response :: 200</div>}
      </header>

      <motion.div
        className="answer__body-motion"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.42, delay: 0.04, ease: [0.22, 1, 0.36, 1] }}
      >
        {message.phase ? (
          <div className="answer__phase-indicator">
            <span className="answer__phase-spinner" />
            <span className="answer__phase-label">
              {message.phase === "streaming"
                ? "Generating answer…"
                : `Translating to ${message.lang?.toUpperCase() ?? "your language"}…`}
            </span>
          </div>
        ) : (
          <div className="answer__body">
            {blocks.map((block, i) => (
              <motion.div
                key={`${message.id}-b-${i}`}
                className="answer__block-motion"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  duration: 0.4,
                  delay: 0.08 + i * 0.055,
                  ease: [0.22, 1, 0.36, 1],
                }}
              >
                {block.type === "code" ? (
                  <CodeBlock code={block.content} lang={block.lang ?? "text"} />
                ) : (
                  <Prose text={block.content} />
                )}
              </motion.div>
            ))}
          </div>
        )}
      </motion.div>

      {trustedCount > 0 && !devMode && (
        <p className="answer__confidence" role="status">
          <span className="answer__confidence-icon" aria-hidden>
            ✓
          </span>
          Based on {trustedCount} trusted source{trustedCount === 1 ? "" : "s"}
        </p>
      )}

      {showGreetingChips && (
        <div className="answer__suggestions">
          <span className="answer__suggestions-label">Try asking</span>
          <ul className="answer__suggestion-list">
            {GREETING_SUGGESTIONS.map((s) => (
              <li key={s.label}>
                <button
                  type="button"
                  className="answer__suggestion-chip"
                  onClick={() => onQuickPrompt?.(s.prompt)}
                >
                  {s.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {sources.length > 0 && (
        <div className="answer__sources-block">
          {!devMode ? (
            <button
              type="button"
              className="answer__sources-toggle"
              aria-expanded={sourcesOpen}
              onClick={() => setSourcesOpen((o) => !o)}
            >
              <span className="answer__sources-toggle-icon" aria-hidden>
                📚
              </span>
              Sources ({sources.length})
              <ChevronIcon className={sourcesOpen ? "answer__sources-chevron--open" : ""} />
            </button>
          ) : (
            <div className="answer__sources-label answer__sources-label--static">
              <DocIcon /> sources
            </div>
          )}
          {(devMode || sourcesOpen) && (
            <ul className="answer__sources-list">
              {sources.map((s, idx) => (
                <li key={`${s.title}-${idx}`}>
                  {s.has_external_link && s.url ? (
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="answer__source-row"
                    >
                      <SourceIcon source={s} />
                      <span className="src-text">
                        <span className="src-title">{s.title}</span>
                        <span className="src-domain">{sourceSubtitle(s)}</span>
                      </span>
                      <ExternalIcon />
                    </a>
                  ) : (
                    <button
                      type="button"
                      className="answer__source-row answer__source-row--internal"
                      onClick={() => setSelectedSource(s)}
                    >
                      <SourceIcon source={s} />
                      <span className="src-text">
                        <span className="src-title-row">
                          <span className="src-title">{s.title}</span>
                          {isVerifiedInternal(s) && (
                            <span className="src-verified-badge">Verified</span>
                          )}
                        </span>
                        <span className="src-domain">{s.domain || "CanonicalQA index"}</span>
                      </span>
                      <DetailsIcon />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {!devMode && (
        <div className="answer__feedback">
          <span className="answer__feedback-label">Was this helpful?</span>
          <div className="answer__feedback-btns">
            <button
              type="button"
              className={`answer__feedback-btn ${feedback === "up" ? "answer__feedback-btn--active" : ""}`}
              aria-pressed={feedback === "up"}
              aria-label="Yes, helpful"
              onClick={() => setFeedback((f) => (f === "up" ? null : "up"))}
            >
              👍
            </button>
            <button
              type="button"
              className={`answer__feedback-btn ${feedback === "down" ? "answer__feedback-btn--active" : ""}`}
              aria-pressed={feedback === "down"}
              aria-label="Not helpful"
              onClick={() => setFeedback((f) => (f === "down" ? null : "down"))}
            >
              👎
            </button>
          </div>
        </div>
      )}

      {onQuickPrompt && !showGreetingChips && (
        <div className="answer__followups">
          <span className="answer__followups-label">Need more help?</span>
          <ul className="answer__followup-list">
            {FOLLOW_UPS.map((f) => (
              <li key={f.label}>
                <button type="button" className="answer__followup-chip" onClick={() => onQuickPrompt(f.prompt)}>
                  {f.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {selectedSource && (
        <div
          className="source-modal__backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Source details"
          onClick={() => setSelectedSource(null)}
        >
          <div className="source-modal" onClick={(e) => e.stopPropagation()}>
            <div className="source-modal__header">
              <h3>{devMode ? "Source provenance" : "Source"}</h3>
              <button
                type="button"
                className="source-modal__close"
                onClick={() => setSelectedSource(null)}
                aria-label="Close"
              >
                Close
              </button>
            </div>
            {!devMode ? (
              <div className="source-modal__customer">
                <div className="source-modal__title-row">
                  <SourceIcon source={selectedSource} />
                  <p className="source-modal__title">{selectedSource.title}</p>
                </div>
                {isVerifiedInternal(selectedSource) && (
                  <p className="source-modal__verified">Verified internal source</p>
                )}
                <p className="source-modal__domain">{selectedSource.domain || "Indexed corpus"}</p>
                {selectedSource.excerpt && (
                  <blockquote className="source-modal__excerpt">{selectedSource.excerpt}</blockquote>
                )}
              </div>
            ) : (
              <>
                <div className="source-modal__title-row source-modal__title-row--dev">
                  <SourceIcon source={selectedSource} />
                  <p className="source-modal__title source-modal__title--dev">{selectedSource.title}</p>
                </div>
                <div className="source-modal__grid">
                  <div>
                    <strong>Title</strong>
                    <span>{selectedSource.title}</span>
                  </div>
                  <div>
                    <strong>Domain</strong>
                    <span>{selectedSource.domain || "N/A"}</span>
                  </div>
                  <div>
                    <strong>Citation</strong>
                    <span>{selectedSource.citation_index ?? "N/A"}</span>
                  </div>
                  <div>
                    <strong>Fetcher</strong>
                    <span>{selectedSource.retrieval_method ?? "N/A"}</span>
                  </div>
                  <div>
                    <strong>Score</strong>
                    <span>
                      {typeof selectedSource.score === "number" ? selectedSource.score.toFixed(4) : "N/A"}
                    </span>
                  </div>
                  <div>
                    <strong>Chunk ID</strong>
                    <span>{selectedSource.chunk_id || "N/A"}</span>
                  </div>
                </div>
                <div className="source-modal__section">
                  <strong>Matched excerpt</strong>
                  <pre>{selectedSource.excerpt || "No excerpt available."}</pre>
                </div>
                <div className="source-modal__section">
                  <strong>All metadata</strong>
                  <pre>{JSON.stringify(selectedSource.metadata ?? {}, null, 2)}</pre>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {devMode && (message.traceUrl || message.latencyBreakdownMs) && (
        <footer className="answer__trace">
          <div className="answer__trace-row">
            <span className="answer__trace-label">diagnostics</span>
            <span className="answer__trace-cache">
              {message.fromCache ? "cache :: hit" : "cache :: miss"}
            </span>
            {message.traceUrl && (
              <a href={message.traceUrl} target="_blank" rel="noreferrer">
                download trace json
              </a>
            )}
          </div>
          {message.latencyBreakdownMs && (
            <ul>
              {Object.entries(message.latencyBreakdownMs).map(([k, v]) => (
                <li key={k}>
                  <span>{k}</span>
                  <strong>{typeof v === "number" ? v.toFixed(1) : String(v)} ms</strong>
                </li>
              ))}
            </ul>
          )}
          {message.retrievalTrace && message.retrievalTrace.length > 0 && (
            <ul className="answer__trace-fetchers">
              {message.retrievalTrace.map((t, idx) => (
                <li key={`${t.fetcher}-${idx}`}>
                  <span>{t.fetcher}</span>
                  <strong>{Number(t.latency_ms ?? 0).toFixed(1)} ms</strong>
                  <em>{t.results_returned} docs</em>
                  {t.error ? <small>error: {t.error}</small> : null}
                </li>
              ))}
            </ul>
          )}
          {message.routing ? (
            <pre className="answer__trace-routing">{JSON.stringify(message.routing, null, 2)}</pre>
          ) : null}
        </footer>
      )}
    </motion.article>
  );
};

const Prose: React.FC<{ text: string }> = ({ text }) => {
  const paras = text.split(/\n\n+/).filter((p) => p.trim().length > 0);
  return (
    <div className="answer__prose-wrap">
      {paras.map((para, pi) => {
        const parts = para.split(/(`[^`]+`)/g);
        return (
          <p key={pi} className="answer__prose">
            {parts.map((part, i) =>
              part.startsWith("`") && part.endsWith("`") ? (
                <code key={i} className="inline-code">
                  {part.slice(1, -1)}
                </code>
              ) : (
                <span key={i}>
                  {part.split("\n").map((line, li, arr) => (
                    <span key={li}>
                      {line}
                      {li < arr.length - 1 ? <br /> : null}
                    </span>
                  ))}
                </span>
              )
            )}
          </p>
        );
      })}
    </div>
  );
};

const CodeBlock: React.FC<{ code: string; lang: string }> = ({ code, lang }) => {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    void navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="codeblock">
      <div className="codeblock__bar">
        <span className="codeblock__lang">{lang}</span>
        <button type="button" onClick={handleCopy} className="codeblock__copy">
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre>
        <code dangerouslySetInnerHTML={{ __html: highlight(code) }} />
      </pre>
    </div>
  );
};

const DocIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
  </svg>
);

const ExternalIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    <polyline points="15 3 21 3 21 9" />
    <line x1="10" y1="14" x2="21" y2="3" />
  </svg>
);

const DetailsIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="16" x2="12" y2="12" />
    <line x1="12" y1="8" x2="12.01" y2="8" />
  </svg>
);

const ChevronIcon = ({ className }: { className?: string }) => (
  <svg
    className={`answer__sources-chevron ${className ?? ""}`}
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    aria-hidden
  >
    <polyline points="6 9 12 15 18 9" />
  </svg>
);
