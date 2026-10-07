"""
Audio module: speech-to-text, language detection, and mixed-language transcription via Whisper.
"""

from audio.chunk import (
    ChunkedTranscriptionResult,
    ChunkResult,
    transcribe_chunked,
)
from audio.transcribe import (
    SpeechToEnglishResult,
    TranscriptionResult,
    clear_model_cache,
    transcribe_file,
    translate_speech_to_english,
)

__all__ = [
    "ChunkedTranscriptionResult",
    "ChunkResult",
    "SpeechToEnglishResult",
    "TranscriptionResult",
    "clear_model_cache",
    "transcribe_chunked",
    "transcribe_file",
    "translate_speech_to_english",
]
