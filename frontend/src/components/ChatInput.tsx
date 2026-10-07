// src/components/ChatInput.tsx
import React, { useState } from "react";
import SpeechRecognition, { useSpeechRecognition } from "react-speech-recognition";

import { API_BASE_URL } from "../config";

interface LanguageDetectionResponse {
  detected_language: string;
  text: string;
}

interface ChatInputProps {
  onSubmit: (text: string, mode: "speech" | "text", detectedLanguage?: string) => void;
  disabled?: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSubmit, disabled = false }) => {
  const [input, setInput] = useState("");
  const [detectedLanguage, setDetectedLanguage] = useState<string | null>(null);
  const [isDetecting, setIsDetecting] = useState(false);
  const { transcript, listening, resetTranscript } = useSpeechRecognition();

  const handleSpeechStart = () => {
    if (disabled) return;
    SpeechRecognition.startListening({ continuous: true });
  };

  const handleSpeechStop = async () => {
    SpeechRecognition.stopListening();
    const spoken = transcript.trim();
    if (spoken) {
      const detected = await detectLanguage(spoken);
      onSubmit(spoken, "speech", detected ?? undefined);
    }
    resetTranscript();
  };

  const handleTextSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!input.trim() || disabled) return;
    const detected = await detectLanguage(input);
    onSubmit(input, "text", detected ?? undefined);
    setInput("");
  };

  const detectLanguage = async (text: string): Promise<string | null> => {
    setIsDetecting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/detect-language`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

      if (!response.ok) {
        throw new Error("Detection failed");
      }

      const data: LanguageDetectionResponse = await response.json();
      setDetectedLanguage(data.detected_language);
      return data.detected_language;
    } catch (error) {
      console.error(error);
      return null;
    } finally {
      setIsDetecting(false);
    }
  };

  return (
    <div className="chat-input">
      <form onSubmit={handleTextSubmit} className="chat-input__form">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Type your question..."
          className="chat-input__field"
          aria-label="Message"
          disabled={disabled}
        />
        <button type="submit" className="btn btn--primary" disabled={!input.trim() || disabled}>
          Send
        </button>
      </form>

      <div className="chat-input__speech">
        {listening ? (
          <button type="button" onClick={handleSpeechStop} className="btn btn--danger" disabled={disabled}>
            Stop speaking
          </button>
        ) : (
          <button type="button" onClick={handleSpeechStart} className="btn btn--secondary" disabled={disabled}>
            Hold to speak
          </button>
        )}
        <p className="chat-input__hint">{listening ? "Listening…" : "Or press the mic to talk"}</p>
        {detectedLanguage && (
          <span className="chat-input__language">
            Detected language: {isDetecting ? "..." : detectedLanguage.toUpperCase()}
          </span>
        )}
      </div>
    </div>
  );
};
