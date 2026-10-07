import { useCallback, useEffect, useRef, useState } from "react";
import {
  API_BASE_URL,
  FORCE_BROWSER_SPEECH,
  WHISPER_MODEL,
  WHISPER_SOURCE_LANGUAGE_HINT,
  WHISPER_TRANSLATE_MODEL,
} from "../config";

export type MicPhase =
  | "idle"
  | "browser_listening"
  | "media_recording"
  | "transcribing";

export interface TranscribeResult {
  pipeline?: "chunked" | "simple";
  merged_text: string;
  text_english: string;
  source_language: string;
  source_language_name?: string | null;
  is_multilingual: boolean;
  chunks: Array<{
    index: number;
    start_label: string;
    end_label: string;
    language: string;
    language_name?: string | null;
    text: string;
  }>;
}

interface UseMicPipelineOptions {
  sourceLanguageHint?: string;
  preferredPipeline?: "chunked" | "simple" | "auto";
}

/**
 * Probes GET /audio/capabilities on the brain; when Whisper is available, the mic
 * uses MediaRecorder → POST /audio/transcribe (chunked pipeline). Otherwise falls
 * back to react-speech-recognition (browser STT).
 */
export function useMicPipeline(options?: UseMicPipelineOptions) {
  const [whisperAvailable, setWhisperAvailable] = useState<boolean | null>(
    FORCE_BROWSER_SPEECH ? false : null
  );
  /** Whisper HTTP pipeline when upload is sent (matches brain query param). */
  const [whisperPipeline, setWhisperPipeline] = useState<"chunked" | "simple">(
    options?.preferredPipeline === "simple" ? "simple" : "chunked"
  );
  const [phase, setPhase] = useState<MicPhase>("idle");
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  useEffect(() => {
    let cancelled = false;
    if (FORCE_BROWSER_SPEECH) {
      return;
    }
    fetch(`${API_BASE_URL}/audio/capabilities`)
      .then((r) => (r.ok ? r.json() : null))
      .then(
        (
          data: {
            chunked_whisper?: boolean;
            simple_whisper?: boolean;
            recommended_mic_pipeline?: string | null;
          } | null
        ) => {
          if (cancelled || !data) return;
          const ok = !!data.chunked_whisper || !!data.simple_whisper;
          setWhisperAvailable(ok);

          const preferred = options?.preferredPipeline ?? "auto";
          if (preferred === "chunked" && data.chunked_whisper) {
            setWhisperPipeline("chunked");
            return;
          }
          if (preferred === "simple" && data.simple_whisper) {
            setWhisperPipeline("simple");
            return;
          }

          // Auto mode: follow backend recommendation, then fall back.
          if (data.recommended_mic_pipeline === "simple" && data.simple_whisper) {
            setWhisperPipeline("simple");
          } else if (data.chunked_whisper) {
            setWhisperPipeline("chunked");
          } else if (data.simple_whisper) {
            setWhisperPipeline("simple");
          }
        }
      )
      .catch(() => {
        if (!cancelled) setWhisperAvailable(false);
      });
    return () => {
      cancelled = true;
    };
  }, [options?.preferredPipeline]);

  const stopMediaStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const transcribeBlob = useCallback(async (blob: Blob): Promise<TranscribeResult> => {
    const fd = new FormData();
    fd.append("file", blob, "recording.webm");
    const qs = new URLSearchParams();
    qs.set("pipeline", whisperPipeline);
    qs.set("model_size", WHISPER_MODEL);
    if (WHISPER_TRANSLATE_MODEL) {
      qs.set("translate_model_size", WHISPER_TRANSLATE_MODEL);
    }
    const hint = options?.sourceLanguageHint?.trim() || WHISPER_SOURCE_LANGUAGE_HINT;
    if (hint) {
      qs.set("source_language_hint", hint);
    }
    const url = `${API_BASE_URL}/audio/transcribe?${qs.toString()}`;
    const res = await fetch(url, { method: "POST", body: fd });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(err || res.statusText);
    }
    return res.json();
  }, [options?.sourceLanguageHint, whisperPipeline]);

  const startMediaRecording = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("getUserMedia is not available");
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;
    chunksRef.current = [];
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "audio/mp4";
    const rec = new MediaRecorder(stream, { mimeType: mime });
    mediaRecorderRef.current = rec;
    rec.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    rec.start(250);
    setPhase("media_recording");
  }, []);

  const stopMediaRecordingAndTranscribe = useCallback(async (): Promise<TranscribeResult | null> => {
    const rec = mediaRecorderRef.current;
    if (!rec || rec.state === "inactive") {
      stopMediaStream();
      setPhase("idle");
      return null;
    }
    const mimeType = rec.mimeType;
    await new Promise<void>((resolve) => {
      rec.onstop = () => resolve();
      rec.stop();
    });
    mediaRecorderRef.current = null;
    stopMediaStream();
    const blob = new Blob(chunksRef.current, { type: mimeType || "audio/webm" });
    chunksRef.current = [];
    if (blob.size < 256) {
      setPhase("idle");
      return null;
    }
    setPhase("transcribing");
    try {
      const out = await transcribeBlob(blob);
      setPhase("idle");
      return out;
    } catch (e) {
      setPhase("idle");
      throw e;
    }
  }, [stopMediaStream, transcribeBlob]);

  const cancelMediaRecording = useCallback(async () => {
    const rec = mediaRecorderRef.current;
    if (!rec || rec.state === "inactive") {
      stopMediaStream();
      chunksRef.current = [];
      setPhase("idle");
      return;
    }
    await new Promise<void>((resolve) => {
      rec.onstop = () => resolve();
      rec.stop();
    });
    mediaRecorderRef.current = null;
    chunksRef.current = [];
    stopMediaStream();
    setPhase("idle");
  }, [stopMediaStream]);

  return {
    whisperAvailable,
    whisperPipeline,
    phase,
    setPhase,
    startMediaRecording,
    stopMediaRecordingAndTranscribe,
    cancelMediaRecording,
  };
}
