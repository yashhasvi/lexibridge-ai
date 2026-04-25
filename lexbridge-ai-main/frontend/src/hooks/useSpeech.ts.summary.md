# File: useSpeech.ts

## Purpose
Provides a hook for streaming MP3 audio from the backend edge-TTS endpoint and falls back to browser speech synthesis if the fetch fails.

## Key Components
- `useSpeech` hook returns an object with three properties:
  - `speakText`: Function to speak text asynchronously.
  - `stopSpeaking`: Function to stop speaking.
  - `isSpeakable`: Constant indicating whether speech is supported (always true in this implementation).
  - `isSpeaking`: State variable tracking whether speech is currently active.

## Important Logic
- The hook uses the `AbortController` API to manage requests and prevent memory leaks.
- It utilizes the `speechSynthesis` API as a fallback if the TTS endpoint fails or is not available.
- The `speakText` function cleans the input text by removing citation markers and excess whitespace before sending it to the TTS endpoint.

## Dependencies
- React hooks (`useCallback`, `useMemo`, `useState`, `useRef`)
- Fetch API for making requests to the TTS endpoint
- SpeechSynthesis API (for browser fallback)
- AbortController API

## Notes
- The hook assumes that the backend edge-TTS endpoint is available at `${API_BASE_URL}/audio/speak`.
- It uses a basic string replacement approach to clean the input text, which might not be sufficient for all possible text formats.