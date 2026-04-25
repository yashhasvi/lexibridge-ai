// src/components/ChatThread.tsx
import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { Message } from "../App";
import { useUiMode } from "../contexts/UiModeContext";
import { AnswerCard } from "./AnswerCard";
import { ProcessingIndicator } from "./ProcessingIndicator";

interface ChatThreadProps {
  messages: Message[];
  isProcessing: boolean;
  onQuickPrompt: (text: string) => void;
  onSpeakMessage: (text: string, lang?: string) => void;
  onStopSpeaking: () => void;
  isSpeakable: boolean;
  isSpeaking: boolean;
}

export const ChatThread: React.FC<ChatThreadProps> = ({
  messages,
  isProcessing,
  onQuickPrompt,
  onSpeakMessage,
  onStopSpeaking,
  isSpeakable,
  isSpeaking,
}) => {
  const { devMode } = useUiMode();
  const threadRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const lastMessage = messages[messages.length - 1];
  const showProcessingIndicator =
    isProcessing &&
    (lastMessage?.sender !== "pebble" || Boolean(lastMessage?.phase));

  useEffect(() => {
    const container = threadRef.current;
    if (!container) return;
    const raf = window.requestAnimationFrame(() => {
      container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
      endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    });
    return () => window.cancelAnimationFrame(raf);
  }, [messages.length, isProcessing]);

  useEffect(() => {
    const container = threadRef.current;
    if (!container) return;
    const onScroll = () => {
      const distanceFromBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      setShowJumpToLatest(distanceFromBottom > 140);
    };
    onScroll();
    container.addEventListener("scroll", onScroll, { passive: true });
    return () => container.removeEventListener("scroll", onScroll);
  }, []);

  const jumpToLatest = () => {
    const container = threadRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  };

  const copyUserMessage = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedMessageId(id);
      window.setTimeout(() => {
        setCopiedMessageId((current) => (current === id ? null : current));
      }, 1200);
    } catch {
      // no-op: clipboard may be blocked in some contexts
    }
  };

  return (
    <div className="thread" ref={threadRef}>
      <div className="thread__inner">
        {messages.map((msg, idx) =>
          msg.sender === "user" ? (
            <motion.div
              key={msg.id}
              className="user-msg"
              data-msg-id={msg.id}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
              onDoubleClick={() => copyUserMessage(msg.id, msg.text)}
              title="Double-click to copy"
            >
              {devMode && (
                <div className="user-msg__meta">
                  <span>user :: query</span>
                  {msg.mode === "speech" && <span className="user-msg__badge">voice</span>}
                </div>
              )}
              {!devMode && msg.mode === "speech" && (
                <div className="user-msg__meta user-msg__meta--minimal">
                  <span className="user-msg__badge user-msg__badge--minimal">Voice</span>
                </div>
              )}
              <p className="user-msg__text">{msg.text}</p>
              {copiedMessageId === msg.id && (
                <span className="user-msg__copied">Copied</span>
              )}
            </motion.div>
          ) : (
            <AnswerCard
              key={msg.id}
              message={msg}
              previousUserText={
                messages[idx - 1]?.sender === "user" ? messages[idx - 1].text : undefined
              }
              onQuickPrompt={onQuickPrompt}
              onSpeak={onSpeakMessage}
              onStop={onStopSpeaking}
              isSpeakable={isSpeakable}
              isSpeaking={isSpeaking}
            />
          )
        )}

        {showProcessingIndicator && <ProcessingIndicator />}

        {showJumpToLatest && (
          <button
            type="button"
            className="thread__jump"
            onClick={jumpToLatest}
            aria-label="Jump to latest message"
          >
            Jump to latest ↓
          </button>
        )}

        <div ref={endRef} />
      </div>
    </div>
  );
};
