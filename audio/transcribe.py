"""
Whisper-backed speech recognition: transcript text and detected spoken language.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

try:
    import whisper
except ImportError:  # pragma: no cover - optional until installed
    whisper = None  # type: ignore


@dataclass(frozen=True)
class TranscriptionResult:
    """Outcome of transcribing an audio file."""

    text: str
    language: str
    """Whisper language code (e.g. ``en``, ``ja``)."""
    language_name: Optional[str] = None
    """Full name when available from Whisper's tokenizer."""


@dataclass(frozen=True)
class SpeechToEnglishResult:
    """Speech translated to English; ``source_language`` is the detected spoken language."""

    text_english: str
    source_language: str
    """Whisper language code for the audio that was spoken (e.g. ``ja``, ``es``)."""
    source_language_name: Optional[str] = None


_model_cache: dict[str, Any] = {}
_ffmpeg_path_done = False


def _ensure_ffmpeg_on_path() -> None:
    """Whisper decodes audio via ``ffmpeg``; some shells (e.g. IDE) omit Homebrew's bin."""
    global _ffmpeg_path_done
    if _ffmpeg_path_done:
        return
    _ffmpeg_path_done = True
    if shutil.which("ffmpeg"):
        return
    for bindir in ("/opt/homebrew/bin", "/usr/local/bin"):
        if Path(bindir, "ffmpeg").is_file():
            os.environ["PATH"] = bindir + os.pathsep + os.environ.get("PATH", "")
            logger.debug("Prepended %s to PATH for ffmpeg.", bindir)
            return


def _resolve_audio_path(audio_path: Union[str, Path]) -> Path:
    path = Path(audio_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")
    return path


def _language_name(code: str) -> Optional[str]:
    if whisper is None:
        return None
    try:
        from whisper.tokenizer import LANGUAGES

        return LANGUAGES.get(code)
    except Exception:  # pragma: no cover
        return None


def _get_model(model_size: str, device: Optional[str] = None) -> Any:
    if whisper is None:
        raise ImportError(
            "openai-whisper is not installed. Install with: pip install -r audio/requirements.txt "
            "(and ensure ffmpeg is installed)."
        )
    _ensure_ffmpeg_on_path()
    if model_size not in _model_cache:
        _model_cache[model_size] = whisper.load_model(model_size, device=device)
    return _model_cache[model_size]


def transcribe_file(
    audio_path: Union[str, Path],
    *,
    model_size: str = "base",
    device: Optional[str] = None,
    language: Optional[str] = None,
    task: str = "transcribe",
    **transcribe_options: Any,
) -> TranscriptionResult:
    """
    Transcribe audio and return text plus detected (or forced) language.

    Use a **multilingual** model (e.g. ``base``, ``small``, ``medium``, ``large``) for
    reliable language detection on non-English audio. English-only checkpoints (names
    ending in ``.en``) always treat the language as English.

    Parameters
    ----------
    audio_path:
        Path to an audio file (formats supported by ffmpeg — wav, mp3, flac, etc.).
    model_size:
        Whisper model id: ``tiny``, ``base``, ``small``, ``medium``, ``large``, ``turbo``, etc.
    device:
        ``cuda``, ``cpu``, or ``None`` for default.
    language:
        If set, skip detection and decode as this language (Whisper CLI-style name, e.g. ``English``).
    task:
        ``transcribe`` or ``translate`` (translation to English; avoid ``turbo`` for translate).
    transcribe_options:
        Passed through to ``model.transcribe()`` (e.g. ``fp16=False`` on CPU).
    """
    path = _resolve_audio_path(audio_path)

    model = _get_model(model_size, device=device)
    result = model.transcribe(
        str(path),
        language=language,
        task=task,
        **transcribe_options,
    )

    lang_code = (result.get("language") or "").strip() or "unknown"
    text = (result.get("text") or "").strip()

    return TranscriptionResult(
        text=text,
        language=lang_code,
        language_name=_language_name(lang_code),
    )


def translate_speech_to_english(
    audio_path: Union[str, Path],
    *,
    model_size: str = "medium",
    device: Optional[str] = None,
    source_language: Optional[str] = None,
    **transcribe_options: Any,
) -> SpeechToEnglishResult:
    """
    Translate spoken content to English and return the detected source language.

    Whisper's ``task="translate"`` maps non-English speech to English text. The
    ``source_language`` field is the model's guess at what was spoken—persist it
    if you need to remember the original language for later (e.g. translating
    answers back).

    Prefer multilingual models ``small``, ``medium``, or ``large``. The ``turbo``
    checkpoint is not intended for translation and may ignore translate mode.

    Parameters
    ----------
    audio_path:
        Path to an audio file (formats supported by ffmpeg).
    model_size:
        Whisper model id; default ``medium`` balances quality and speed for translate.
    device:
        ``cuda``, ``cpu``, or ``None`` for default.
    source_language:
        If set, decode as this language (Whisper name, e.g. ``Japanese``). Detection
        is skipped when provided.
    transcribe_options:
        Passed through to ``model.transcribe()`` (e.g. ``fp16=False`` on CPU).
    """
    path = _resolve_audio_path(audio_path)
    model = _get_model(model_size, device=device)
    result = model.transcribe(
        str(path),
        language=source_language,
        task="translate",
        **transcribe_options,
    )

    lang_code = (result.get("language") or "").strip() or "unknown"
    text = (result.get("text") or "").strip()

    return SpeechToEnglishResult(
        text_english=text,
        source_language=lang_code,
        source_language_name=_language_name(lang_code),
    )


def clear_model_cache() -> None:
    """Drop loaded Whisper models to free VRAM/RAM."""
    _model_cache.clear()
