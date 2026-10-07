// src/hooks/useSpeech.ts
import { useCallback, useMemo, useRef, useState } from "react";
import { API_BASE_URL } from "../config";

/**
 * Streams MP3 audio from the backend edge-tts endpoint (`POST /audio/speak`).
 * Falls back to browser `speechSynthesis` only if the fetch itself fails
 * (e.g. backend is down).
 */
export const useSpeech = () => {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const stopSpeaking = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.removeAttribute("src");
      audioRef.current.load();
      audioRef.current = null;
    }
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setIsSpeaking(false);
  }, []);

  const speakText = useCallback(
    async (text: string, lang?: string) => {
      stopSpeaking();

      // Strip citation markers like [1], [2][3], and stray brackets before speaking
      const clean = text
        .replace(/\[\d+\]/g, "")
        .replace(/\s{2,}/g, " ")
        .trim();

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await fetch(`${API_BASE_URL}/audio/speak`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: clean, lang: lang ?? "en" }),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) throw new Error("TTS fetch failed");

        const reader = res.body.getReader();
        const chunks: Uint8Array[] = [];
        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          chunks.push(value);
        }

        if (controller.signal.aborted) return;

        const blob = new Blob(chunks, { type: "audio/mpeg" });
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audioRef.current = audio;

        audio.onplay = () => setIsSpeaking(true);
        audio.onended = () => {
          setIsSpeaking(false);
          URL.revokeObjectURL(url);
          audioRef.current = null;
        };
        audio.onerror = () => {
          setIsSpeaking(false);
          URL.revokeObjectURL(url);
          audioRef.current = null;
        };

        await audio.play();
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") return;

        // Fallback: browser speechSynthesis
        if ("speechSynthesis" in window) {
          window.speechSynthesis.cancel();
          const utterance = new SpeechSynthesisUtterance(clean);
          utterance.lang = lang ?? "en-US";
          const voices = window.speechSynthesis.getVoices();
          const match = voices.find((v) => v.lang.startsWith(lang ?? "en"));
          if (match) utterance.voice = match;
          utterance.onstart = () => setIsSpeaking(true);
          utterance.onend = () => setIsSpeaking(false);
          utterance.onerror = () => setIsSpeaking(false);
          window.speechSynthesis.speak(utterance);
        }
      }
    },
    [stopSpeaking],
  );

  return useMemo(
    () => ({
      speakText,
      stopSpeaking,
      isSpeakable: true as const,
      isSpeaking,
    }),
    [isSpeaking, speakText, stopSpeaking],
  );
};
