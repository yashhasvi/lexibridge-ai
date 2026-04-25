// src/components/PromptBar.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Keyboard from "react-simple-keyboard";
import KeyboardLayouts from "simple-keyboard-layouts";
import SpeechRecognition, {
  useSpeechRecognition,
} from "react-speech-recognition";
import { API_BASE_URL, WHISPER_SOURCE_LANGUAGE_HINT } from "../config";
import { useUiMode } from "../contexts/UiModeContext";
import { useMicPipeline } from "../hooks/useMicPipeline";
import "react-simple-keyboard/build/css/index.css";

export interface SubmitMeta {
  detectedLanguage?: string;
  /** When set (e.g. Whisper translate pass), skips text→English translation before RAG. */
  englishQuery?: string;
}

interface PromptBarProps {
  onSubmit: (
    text: string,
    mode: "speech" | "text",
    meta?: SubmitMeta
  ) => void;
  disabled?: boolean;
}

const CHITCHAT_PATTERN =
  /^\s*(hi|hello|hey|yo|hola|namaste|good (morning|afternoon|evening)|how are you|how's it going|what's up|sup|thanks|thank you|thx)\s*[!.?]*\s*$/i;

const SURPRISE_PROMPTS = [
  "Give me a weird but true computer science fact.",
  "Explain neural networks like a comic story.",
  "What’s one underrated algorithm every engineer should know?",
  "Ask me one question and then teach me something based on my answer.",
  "Turn this into a mini quiz with 3 questions: retrieval-augmented generation.",
];

const SPEECH_LANGUAGE_OPTIONS = [
  { value: "", label: "Auto" },
  { value: "en", label: "English" },
  { value: "te", label: "Telugu" },
  { value: "hi", label: "Hindi" },
  { value: "kn", label: "Kannada" },
  { value: "ml", label: "Malayalam" },
];

const KEYBOARD_LAYOUT_OPTIONS = [
  { value: "english", label: "English" },
  { value: "hindi", label: "Hindi" },
  { value: "telugu", label: "Telugu" },
  { value: "kannada", label: "Kannada" },
  { value: "malayalam", label: "Malayalam" },
  { value: "arabic", label: "Arabic" },
  { value: "russian", label: "Russian" },
  { value: "japanese", label: "Japanese" },
];

const KEYBOARD_LANG_STORAGE_KEY = "pebble.keyboard.lang";

/** Merged onto keys by react-simple-keyboard — styled in App.css */
const KEYBOARD_BUTTON_THEME = [
  { class: "pebble-key--mod", buttons: "{shift} {tab} {lock} {bksp}" },
  { class: "pebble-key--accent", buttons: "{enter}" },
  { class: "pebble-key--space", buttons: "{space}" },
  { class: "pebble-key--utility", buttons: ".com @" },
];
const DEFAULT_KEYBOARD_LAYOUT: {
  layout: Record<string, string[]>;
  display: Record<string, string>;
} = {
  layout: {
    default: [
      "` 1 2 3 4 5 6 7 8 9 0 - = {bksp}",
      "{tab} q w e r t y u i o p [ ] \\",
      "{lock} a s d f g h j k l ; ' {enter}",
      "{shift} z x c v b n m , . / {shift}",
      ".com @ {space}",
    ],
    shift: [
      "~ ! @ # $ % ^ & * ( ) _ + {bksp}",
      "{tab} Q W E R T Y U I O P { } |",
      '{lock} A S D F G H J K L : " {enter}',
      "{shift} Z X C V B N M < > ? {shift}",
      ".com @ {space}",
    ],
  },
  display: {
    "{bksp}": "⌫",
    "{enter}": "enter",
    "{shift}": "shift",
    "{space}": "space",
    "{tab}": "tab",
    "{lock}": "caps",
  },
};

export const PromptBar: React.FC<PromptBarProps> = ({ onSubmit, disabled = false }) => {
  const { devMode } = useUiMode();
  const [input, setInput] = useState("");
  const [lastWhisperDebug, setLastWhisperDebug] = useState<{
    transcript: string;
    language: string;
    languageName?: string | null;
    english: string;
    multilingual: boolean;
    hintUsed?: string;
    pipeline?: string;
  } | null>(null);
  const [speechLanguageHint, setSpeechLanguageHint] = useState<string>(
    WHISPER_SOURCE_LANGUAGE_HINT || ""
  );
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const [activeInputMode, setActiveInputMode] = useState<"keyboard" | "voice" | null>(null);
  const [keyboardLang, setKeyboardLang] = useState(() => {
    if (typeof window === "undefined") return "english";
    const saved = window.localStorage.getItem(KEYBOARD_LANG_STORAGE_KEY)?.trim().toLowerCase();
    if (!saved) return "english";
    const isSupported = KEYBOARD_LAYOUT_OPTIONS.some((o) => o.value === saved);
    return isSupported ? saved : "english";
  });
  const [keyboardLayoutName, setKeyboardLayoutName] = useState<"default" | "shift">("default");
  const { transcript, listening, resetTranscript, browserSupportsSpeechRecognition } =
    useSpeechRecognition();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const keyboardRef = useRef<{
    setInput: (input: string) => void;
  } | null>(null);
  const keyboardLayouts = useMemo(() => new KeyboardLayouts(), []);

  const {
    whisperAvailable,
    whisperPipeline,
    phase,
    startMediaRecording,
    stopMediaRecordingAndTranscribe,
    cancelMediaRecording,
  } = useMicPipeline({
    sourceLanguageHint: speechLanguageHint || undefined,
    preferredPipeline: "chunked",
  });

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 180)}px`;
  }, [input]);

  const activeText = listening && transcript ? transcript : input;

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(KEYBOARD_LANG_STORAGE_KEY, keyboardLang);
  }, [keyboardLang]);

  const selectedKeyboardLayout = useMemo(() => {
    try {
      const candidate = keyboardLayouts.get(keyboardLang) as
        | {
            layout?: Record<string, string[]>;
            display?: Record<string, string>;
          }
        | undefined;
      if (candidate?.layout?.default && candidate.layout.shift) {
        return {
          layout: candidate.layout,
          display: candidate.display,
        };
      }
      return DEFAULT_KEYBOARD_LAYOUT;
    } catch {
      return DEFAULT_KEYBOARD_LAYOUT;
    }
  }, [keyboardLang, keyboardLayouts]);

  const keyboardLayout = selectedKeyboardLayout.layout;
  const keyboardDisplay = selectedKeyboardLayout.display;

  useEffect(() => {
    if (!keyboardVisible) return;
    keyboardRef.current?.setInput(activeText);
  }, [activeText, keyboardVisible]);

  const detectLanguage = async (text: string): Promise<string | undefined> => {
    try {
      const res = await fetch(`${API_BASE_URL}/detect-language`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) return undefined;
      const data = await res.json();
      return data.detected_language;
    } catch {
      return undefined;
    }
  };

  const submitText = async () => {
    const value = input.trim();
    if (!value || disabled) return;
    setInput("");
    if (CHITCHAT_PATTERN.test(value)) {
      onSubmit(value, "text", { detectedLanguage: "en", englishQuery: value });
      return;
    }
    const detected = await detectLanguage(value);
    onSubmit(value, "text", { detectedLanguage: detected });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submitText();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitText();
    }
  };

  const handleSurprisePrompt = () => {
    if (disabled || phase === "transcribing") return;
    const prompt =
      SURPRISE_PROMPTS[Math.floor(Math.random() * SURPRISE_PROMPTS.length)];
    onSubmit(prompt, "text", { detectedLanguage: "en" });
  };

  const handleKeyboardKeyPress = (button: string) => {
    if (button === "{shift}" || button === "{lock}") {
      setKeyboardLayoutName((prev) => (prev === "default" ? "shift" : "default"));
      return;
    }
    if (button === "{enter}") {
      void submitText();
    }
  };

  const useWhisperMic = whisperAvailable === true;

  const switchToKeyboard = async () => {
    // Latest choice wins: if voice is active, stop/cancel it before showing keyboard.
    if (useWhisperMic && phase === "media_recording") {
      await cancelMediaRecording();
    } else if (!useWhisperMic && listening) {
      const spoken = transcript.trim();
      if (spoken) setInput(spoken);
      SpeechRecognition.stopListening();
      resetTranscript();
    }
    setKeyboardVisible(true);
    setActiveInputMode("keyboard");
  };

  const toggleKeyboard = async () => {
    if (keyboardVisible) {
      setKeyboardVisible(false);
      if (activeInputMode === "keyboard") setActiveInputMode(null);
      return;
    }
    await switchToKeyboard();
  };

  const handleMicToggle = async () => {
    if (disabled) return;
    if (keyboardVisible) {
      setKeyboardVisible(false);
    }
    setActiveInputMode("voice");

    if (useWhisperMic) {
      if (phase === "transcribing") return;
      if (phase === "media_recording") {
        try {
          const whisperResult = await stopMediaRecordingAndTranscribe();
          const merged = whisperResult?.merged_text?.trim();
          if (!merged || !whisperResult) return;
          const en = (whisperResult.text_english || merged).trim();
          const sourceLanguage = whisperResult.source_language || "unknown";
          const sourceLanguageName = whisperResult.source_language_name || null;
          const activePipeline = whisperResult.pipeline || whisperPipeline;
          setLastWhisperDebug({
            transcript: merged,
            language: sourceLanguage,
            languageName: sourceLanguageName,
            english: en,
            multilingual: whisperResult.is_multilingual,
            hintUsed: speechLanguageHint || "auto",
            pipeline: activePipeline,
          });
          console.info("[whisper] audio->text", {
            transcript: merged,
            source_language: sourceLanguage,
            source_language_name: sourceLanguageName,
            text_english: en,
            is_multilingual: whisperResult.is_multilingual,
            source_language_hint: speechLanguageHint || "auto",
            pipeline: activePipeline,
            chunks: whisperResult.chunks?.length ?? 0,
          });
          setInput("");
          onSubmit(merged, "speech", {
            detectedLanguage: sourceLanguage || undefined,
            englishQuery: en,
          });
          setActiveInputMode(null);
        } catch (err) {
          console.error(err);
          alert(
            "Whisper transcription failed. Ensure brain has audio deps (whisper, pydub), ffmpeg on PATH, and PYTHONPATH includes the repo root."
          );
        }
        return;
      }
      try {
        await startMediaRecording();
      } catch (e) {
        console.error(e);
        alert("Could not access the microphone.");
      }
      return;
    }

    if (!browserSupportsSpeechRecognition) {
      alert("Voice input isn't supported in this browser. Try Chrome or Edge, or run the brain with Whisper for server-side mic.");
      return;
    }
    if (listening) {
      SpeechRecognition.stopListening();
      const spoken = transcript.trim();
      if (spoken) {
        setInput("");
        if (CHITCHAT_PATTERN.test(spoken)) {
          onSubmit(spoken, "speech", { detectedLanguage: "en", englishQuery: spoken });
          resetTranscript();
          setActiveInputMode(null);
          return;
        }
        const detected = await detectLanguage(spoken);
        onSubmit(spoken, "speech", { detectedLanguage: detected });
      }
      resetTranscript();
      setActiveInputMode(null);
    } else {
      resetTranscript();
      setInput("");
      SpeechRecognition.startListening({ continuous: true });
    }
  };

  const micActive = useWhisperMic ? phase === "media_recording" : listening;
  const showWave = micActive || phase === "transcribing";

  const placeholder = devMode
    ? phase === "transcribing"
      ? "transcribing with Whisper…"
      : micActive
        ? useWhisperMic
          ? "recording… tap mic to stop"
          : "listening…"
        : useWhisperMic
          ? "query the archive, or tap mic for Whisper (server)"
          : "query the archive, or tap mic to speak"
    : phase === "transcribing"
      ? "Transcribing…"
      : micActive
        ? useWhisperMic
          ? "Recording… tap mic when done"
          : "Listening…"
        : "Ask a question…";

  return (
    <>
      <form
        className={`prompt-bar ${micActive ? "prompt-bar--listening" : ""} ${phase === "transcribing" ? "prompt-bar--transcribing" : ""}`}
        onSubmit={handleSubmit}
      >
        {devMode && <span className="prompt-bar__prefix">&gt;_</span>}

        <textarea
          ref={textareaRef}
          value={listening && transcript ? transcript : input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={1}
          disabled={disabled || phase === "transcribing"}
          className="prompt-bar__input"
          aria-label="Ask a question"
        />

        <div className="prompt-bar__actions">
          <button
            type="button"
            className="surprise-btn"
            onClick={handleSurprisePrompt}
            disabled={disabled || phase === "transcribing"}
            aria-label="Send a surprise prompt"
            title="Surprise me"
          >
            ✨
          </button>

          <select
            className="speech-lang-select"
            value={speechLanguageHint}
            onChange={(e) => setSpeechLanguageHint(e.target.value)}
            disabled={disabled || phase === "transcribing" || micActive || !useWhisperMic}
            aria-label="Speech language hint for Whisper"
            title={
              useWhisperMic
                ? "Hint Whisper with your spoken language"
                : "Language hint is available when server Whisper is active"
            }
          >
            {SPEECH_LANGUAGE_OPTIONS.map((option) => (
              <option key={option.value || "auto"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <AnimatePresence>
            {showWave && (
              <motion.div
                key="wave"
                className="waveform"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: "auto" }}
                exit={{ opacity: 0, width: 0 }}
              >
                {Array.from({ length: 14 }).map((_, i) => (
                  <span
                    key={i}
                    className="waveform__bar"
                    style={{ animationDelay: `${i * 0.07}s` }}
                  />
                ))}
              </motion.div>
            )}
          </AnimatePresence>

          <button
            type="button"
            className={`keyboard-toggle-btn ${keyboardVisible ? "keyboard-toggle-btn--active" : ""}`}
            onClick={() => {
              void toggleKeyboard();
            }}
            disabled={disabled || phase === "transcribing"}
            aria-label="Toggle multilingual keyboard"
            title="Toggle multilingual keyboard"
          >
            ⌨
          </button>

          <button
            type="button"
            className={`mic-btn ${micActive ? "mic-btn--active" : ""}`}
            onClick={handleMicToggle}
            disabled={disabled || phase === "transcribing"}
            aria-label={
              phase === "transcribing"
                ? "Transcribing"
                : micActive
                  ? "Stop recording"
                  : useWhisperMic
                    ? "Start Whisper recording"
                    : "Start voice input"
            }
            title={
              useWhisperMic
                ? "Server Whisper (chunked). Tap to start/stop."
                : "Browser speech. Set brain + Whisper for server STT."
            }
          >
            <span className="mic-btn__pulse" />
            <MicIcon />
          </button>

          <button
            type="submit"
            className="send-btn"
            disabled={!input.trim() || disabled || phase === "transcribing"}
            aria-label="Send message"
          >
            <ArrowIcon />
          </button>
        </div>
      </form>

      <AnimatePresence initial={false}>
        {keyboardVisible && (
          <motion.div
            key="keyboard-panel"
            className="keyboard-panel"
            initial={{ opacity: 0, y: 10, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            exit={{ opacity: 0, y: -8, height: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="keyboard-panel__header">
              <span className="keyboard-panel__title">Multilingual keyboard</span>
              <select
                className="keyboard-panel__lang-select"
                value={keyboardLang}
                onChange={(e) => {
                  setKeyboardLang(e.target.value);
                  setKeyboardLayoutName("default");
                }}
                aria-label="Keyboard layout language"
              >
                {KEYBOARD_LAYOUT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <Keyboard
              keyboardRef={(instance) => {
                keyboardRef.current = instance as { setInput: (input: string) => void };
              }}
              onChange={(value) => setInput(value)}
              onKeyPress={handleKeyboardKeyPress}
              layout={keyboardLayout}
              display={keyboardDisplay}
              layoutName={keyboardLayoutName}
              theme="hg-theme-default pebble-keyboard"
              buttonTheme={KEYBOARD_BUTTON_THEME}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {lastWhisperDebug && (
        <div className="whisper-debug" role="status" aria-live="polite">
          <span className="whisper-debug__chip">whisper</span>
          <span className="whisper-debug__line">
            lang: {lastWhisperDebug.language.toUpperCase()}
            {lastWhisperDebug.languageName ? ` (${lastWhisperDebug.languageName})` : ""}
            {lastWhisperDebug.multilingual ? " · multilingual" : ""}
          </span>
          <span className="whisper-debug__line">
            hint: {(lastWhisperDebug.hintUsed || "auto").toUpperCase()}
          </span>
          <span className="whisper-debug__line">
            pipeline: {(lastWhisperDebug.pipeline || whisperPipeline || "chunked").toUpperCase()}
          </span>
          <span className="whisper-debug__line">
            audio→text: {lastWhisperDebug.transcript}
          </span>
          <span className="whisper-debug__line">
            translated/en: {lastWhisperDebug.english}
          </span>
        </div>
      )}
    </>
  );
};

const MicIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="9" y="2" width="6" height="12" rx="3" />
    <path d="M5 10v2a7 7 0 0 0 14 0v-2" />
    <line x1="12" y1="19" x2="12" y2="22" />
  </svg>
);

const ArrowIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
    <line x1="5" y1="12" x2="19" y2="12" />
    <polyline points="13 6 19 12 13 18" />
  </svg>
);
