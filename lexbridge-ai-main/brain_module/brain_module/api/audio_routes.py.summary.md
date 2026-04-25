# File: audio_routes.py

## Purpose
This file defines API routes for audio processing using Whisper STT and edge-tts TTS.

## Key Components

*   **Audio Transcription:** Two transcription methods are supported:
    *   `chunked` (default): silence-split + per-chunk language detection + full translate pass.
    *   `simple`: one-shot transcribe_file.
*   **Text-to-Speech (TTS) via edge-tts**: generates MP3 audio for given text using edge-tts.

## Important Logic

*   Transcription is done either by chunking the audio into smaller parts or by passing the entire audio file at once.
*   For chunked transcription, per-chunk language detection and full translation are performed in addition to silence-splitting.
*   TTS uses the edge-tts library to generate MP3 audio from given text.

## Dependencies

*   **openai-whisper**: required for Whisper STT
*   **pydub** and **ffmpeg**: required for Whisper STT (chunked mode)
*   **edge-tts**: required for TTS

## Notes

*   The API routes are defined using the FastAPI framework.
*   Error handling is done using HTTPException with detailed error messages.
*   Logging is enabled to track important events during processing.