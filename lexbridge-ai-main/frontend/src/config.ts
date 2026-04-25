/** Brain API (FastAPI) — `brain_module` RAG / generate-answer + Whisper upload. */
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8001";

/** If true, skip server Whisper and use the browser Web Speech API for the mic. */
export const FORCE_BROWSER_SPEECH =
  import.meta.env.VITE_FORCE_BROWSER_SPEECH === "true";

/** Whisper model for per-chunk speech->text in /audio/transcribe. */
export const WHISPER_MODEL =
  (import.meta.env.VITE_WHISPER_MODEL as string | undefined)?.trim() || "base";

/**
 * Optional separate Whisper model for the final audio->English pass.
 * Set this to `small` or `medium` for better translation quality.
 */
export const WHISPER_TRANSLATE_MODEL =
  (import.meta.env.VITE_WHISPER_TRANSLATE_MODEL as string | undefined)?.trim() || "";

/**
 * Optional language code hint for Whisper (e.g. te, hi, en) to stabilize decoding.
 * Leave empty to let Whisper auto-detect.
 */
export const WHISPER_SOURCE_LANGUAGE_HINT =
  (import.meta.env.VITE_WHISPER_SOURCE_LANGUAGE_HINT as string | undefined)?.trim() || "";

/**
 * If true, the UI uses in-memory mock generate-answer payloads (no brain_module required).
 * Set in `.env.local`: VITE_DEV_MOCK_API=true
 */
export const DEV_MOCK_API =
  import.meta.env.VITE_DEV_MOCK_API === "true";
