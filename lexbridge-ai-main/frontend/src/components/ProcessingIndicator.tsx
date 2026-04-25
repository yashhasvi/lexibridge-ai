// src/components/ProcessingIndicator.tsx
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { SourceGlyph } from "./SourceGlyph";
import { Skeleton } from "boneyard-js/react";
import { useUiMode } from "../contexts/UiModeContext";

const CUSTOMER_STAGES = [
  "Pebble is thinking…",
  "Searching open QA corpora…",
  "Gathering passages for citations…",
];

const DEV_STAGES = [
  "detect source language",
  "translate → canonical form",
  "query knowledge index",
  "rank candidate passages",
  "synthesise response",
  "verify citations",
];

export const ProcessingIndicator: React.FC = () => {
  const { devMode } = useUiMode();
  const stages = devMode ? DEV_STAGES : CUSTOMER_STAGES;
  const stageCount = stages.length;
  const [stage, setStage] = useState(0);

  useEffect(() => {
    const t = setInterval(() => {
      setStage((s) => (s + 1) % stageCount);
    }, devMode ? 1400 : 1800);
    return () => clearInterval(t);
  }, [devMode, stageCount]);

  return (
    <motion.div
      className="processing"
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
    >
      {devMode ? (
        <div className="processing__terminal">
          <div className="processing__terminal-bar">
            <em>pebble.thinking</em>
            <span style={{ marginLeft: "auto" }}>pid 4821 · running</span>
          </div>
          <div className="processing__terminal-body">
            {stages.slice(0, stage + 1).map((line, i) => (
              <motion.div
                key={i}
                className="processing__line"
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: i === stage ? 1 : 0.45, x: 0 }}
                transition={{ duration: 0.3 }}
              >
                <span className="processing__line-num">{String(i + 1).padStart(2, "0")}</span>
                <span className="processing__prompt">›</span>
                <span>{line}</span>
                {i === stage && <span className="processing__cursor" />}
              </motion.div>
            ))}
          </div>
        </div>
      ) : (
        <div className="processing__customer" aria-live="polite" aria-busy="true">
          <div className="processing__customer-row">
            <span className="processing__thinking-dot" />
            <AnimatePresence mode="wait">
              <motion.span
                key={stage}
                className="processing__customer-text"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.25 }}
              >
                {stages[stage]}
              </motion.span>
            </AnimatePresence>
          </div>
          <LoadingAnswerPreview />
        </div>
      )}

      {devMode && (
        <div className="processing__skeleton">
          <div className="skeleton-line" style={{ width: "92%" }} />
          <div className="skeleton-line" style={{ width: "78%" }} />
          <div className="skeleton-line" style={{ width: "85%" }} />
          <div className="skeleton-line" style={{ width: "60%" }} />
        </div>
      )}
    </motion.div>
  );
};

const LoadingAnswerPreview: React.FC = () => {
  return (
    <Skeleton
      name="chat-answer-preview"
      loading
      animate="shimmer"
      transition
      className="processing__boneyard"
      fallback={
        <div className="processing__skeleton processing__skeleton--soft">
          <div className="skeleton-line" style={{ width: "34%" }} />
          <div className="skeleton-line" style={{ width: "96%" }} />
          <div className="skeleton-line" style={{ width: "84%" }} />
          <div className="skeleton-line" style={{ width: "90%" }} />
          <div className="skeleton-line" style={{ width: "68%" }} />
          <div className="skeleton-line" style={{ width: "42%" }} />
          <div className="skeleton-line" style={{ width: "74%" }} />
          <div className="skeleton-line" style={{ width: "72%" }} />
        </div>
      }
      fixture={<PreviewFixture />}
    >
      <PreviewFixture />
    </Skeleton>
  );
};

const PreviewFixture: React.FC = () => (
  <article className="processing-preview">
    <header className="processing-preview__header">
      <div className="processing-preview__avatar" />
      <div className="processing-preview__title-group">
        <span className="processing-preview__title" />
        <span className="processing-preview__subtitle" />
      </div>
    </header>
    <div className="processing-preview__body">
      <span className="processing-preview__line processing-preview__line--1" />
      <span className="processing-preview__line processing-preview__line--2" />
      <span className="processing-preview__line processing-preview__line--3" />
      <span className="processing-preview__line processing-preview__line--4" />
    </div>
    <section className="processing-preview__sources">
      <span className="processing-preview__sources-label" />
      <div className="processing-preview__source-row">
        <span className="processing-preview__source-icon processing-preview__source-icon--wiki">
          <SourceGlyph type="wikipedia" className="processing-preview__glyph" />
        </span>
        <span className="processing-preview__source-text processing-preview__source-text--1" />
      </div>
      <div className="processing-preview__source-row">
        <span className="processing-preview__source-icon processing-preview__source-icon--internal">
          <SourceGlyph type="internal_index" className="processing-preview__glyph" />
        </span>
        <span className="processing-preview__source-text processing-preview__source-text--2" />
      </div>
    </section>
    <footer className="processing-preview__actions">
      <span className="processing-preview__action-chip" />
      <span className="processing-preview__action-chip" />
      <span className="processing-preview__action-hint" />
    </footer>
  </article>
);
