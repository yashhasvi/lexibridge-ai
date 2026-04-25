"""
Audio API: Whisper STT and edge-tts TTS.

STT  — ``POST /audio/transcribe`` (Whisper, needs ``openai-whisper`` + ``pydub`` + ffmpeg)
TTS  — ``POST /audio/speak``      (edge-tts, needs ``edge-tts`` package)
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audio", tags=["audio"])


def _check_chunked_available() -> None:
    try:
        from audio.chunk import transcribe_chunked  # noqa: F401
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Chunked Whisper unavailable. Install: pip install openai-whisper pydub; "
                "install ffmpeg; set PYTHONPATH to the repository root (see scripts/run_brain_module.sh)."
            ),
        ) from exc


def _check_simple_available() -> None:
    try:
        from audio.transcribe import transcribe_file  # noqa: F401
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Whisper transcribe_file unavailable. Install openai-whisper and set PYTHONPATH "
                "to the repository root."
            ),
        ) from exc


def _run_chunked_sync(
    path: str,
    model_size: str,
    translate_model_size: str | None = None,
    source_language_hint: str | None = None,
) -> dict[str, Any]:
    from audio.chunk import transcribe_chunked

    result = transcribe_chunked(
        path,
        model_size=model_size,
        translate_model_size=translate_model_size,
        source_language_hint=source_language_hint,
    )
    return {
        "pipeline": "chunked",
        "is_multilingual": result.is_multilingual,
        "languages_detected": result.languages_detected,
        "source_language": result.source_language,
        "source_language_name": result.source_language_name,
        "merged_text": result.merged_text,
        "text_english": result.text_english,
        "chunks": [
            {
                "index": c.index,
                "start_ms": c.start_ms,
                "end_ms": c.end_ms,
                "start_label": c.start_label,
                "end_label": c.end_label,
                "language": c.language,
                "language_name": c.language_name,
                "text": c.text,
            }
            for c in result.chunks
        ],
    }


def _run_simple_sync(path: str, model_size: str) -> dict[str, Any]:
    from audio.transcribe import transcribe_file

    r = transcribe_file(path, model_size=model_size)
    return {
        "pipeline": "simple",
        "text": r.text,
        "language": r.language,
        "language_name": r.language_name,
        "merged_text": r.text,
        "text_english": r.text,
        "source_language": r.language,
        "source_language_name": r.language_name,
        "is_multilingual": False,
        "languages_detected": [r.language] if r.language else [],
        "chunks": [],
    }


# ---------------------------------------------------------------------------
# TTS via edge-tts  (POST /audio/speak)
# ---------------------------------------------------------------------------

VOICE_MAP: dict[str, str] = {
    "en": "en-US-BrianMultilingualNeural",
    "hi": "hi-IN-MadhurNeural",
    "ur": "ur-PK-AsadNeural",
    "ar": "ar-SA-HamedNeural",
    "es": "es-ES-AlvaroNeural",
    "fr": "fr-FR-RemyMultilingualNeural",
    "de": "de-DE-FlorianMultilingualNeural",
    "it": "it-IT-GiuseppeMultilingualNeural",
    "pt": "pt-BR-ThalitaMultilingualNeural",
    "ko": "ko-KR-HyunsuMultilingualNeural",
    "ja": "ja-JP-KeitaNeural",
    "zh": "zh-CN-YunxiNeural",
    "ru": "ru-RU-DmitryNeural",
    "bn": "bn-IN-BashkarNeural",
    "ta": "ta-IN-ValluvarNeural",
    "te": "te-IN-ShrutiNeural",
    "mr": "mr-IN-ManoharNeural",
    "gu": "gu-IN-NiranjanNeural",
    "kn": "kn-IN-GaganNeural",
    "ml": "ml-IN-MidhunNeural",
    "pa": "pa-IN-GurpreetNeural",
    "tr": "tr-TR-AhmetNeural",
    "vi": "vi-VN-NamMinhNeural",
    "th": "th-TH-NiwatNeural",
    "pl": "pl-PL-MarekNeural",
    "nl": "nl-NL-MaartenNeural",
    "sv": "sv-SE-MattiasNeural",
    "id": "id-ID-ArdiNeural",
    "ms": "ms-MY-OsmanNeural",
    "uk": "uk-UA-OstapNeural",
    "cs": "cs-CZ-AntoninNeural",
    "ro": "ro-RO-EmilNeural",
    "el": "el-GR-NestorasNeural",
    "hu": "hu-HU-TamasNeural",
    "da": "da-DK-JeppeNeural",
    "fi": "fi-FI-HarriNeural",
    "no": "nb-NO-FinnNeural",
    "he": "he-IL-AvriNeural",
    "fa": "fa-IR-FaridNeural",
    "sw": "sw-KE-RafikiNeural",
    "af": "af-ZA-WillemNeural",
}

FALLBACK_VOICE = "en-US-BrianMultilingualNeural"


def _tts_available() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


def _resolve_voice(lang: str | None) -> str:
    if not lang:
        return FALLBACK_VOICE
    code = lang.strip().lower().split("-")[0].split("_")[0]
    return VOICE_MAP.get(code, FALLBACK_VOICE)


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10_000)
    lang: str | None = Field(None, description="ISO 639-1 language code (e.g. hi, ur, en)")


async def _stream_tts(text: str, voice: str) -> AsyncGenerator[bytes, None]:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]


@router.post("/speak")
async def speak(req: SpeakRequest) -> StreamingResponse:
    """Stream MP3 audio for the given text using edge-tts."""
    if not _tts_available():
        raise HTTPException(
            status_code=503,
            detail="edge-tts not installed. Install: pip install edge-tts",
        )

    voice = _resolve_voice(req.lang)
    logger.info("TTS: lang=%s voice=%s text_len=%d", req.lang, voice, len(req.text))

    return StreamingResponse(
        _stream_tts(req.text, voice),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache",
            "X-TTS-Voice": voice,
        },
    )


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

@router.get("/capabilities")
async def audio_capabilities() -> dict[str, Any]:
    chunked = False
    simple = False
    try:
        from audio.chunk import transcribe_chunked  # noqa: F401

        chunked = True
    except ImportError:
        pass
    try:
        from audio.transcribe import transcribe_file  # noqa: F401

        simple = True
    except ImportError:
        pass
    return {
        "chunked_whisper": chunked,
        "simple_whisper": simple,
        "tts": _tts_available(),
        "recommended_mic_pipeline": "chunked" if chunked else ("simple" if simple else None),
    }


@router.post("/transcribe")
async def transcribe_upload(
    file: UploadFile = File(...),
    pipeline: str = Query(
        "chunked",
        description="chunked = silence-split + per-chunk lang + full translate pass; simple = one-shot transcribe_file",
    ),
    model_size: str = Query("base", description="Whisper model: tiny, base, small, medium, large, …"),
    translate_model_size: str | None = Query(
        None,
        description="Optional Whisper model for final English translation pass; defaults to small when model_size is tiny/base.",
    ),
    source_language_hint: str | None = Query(
        None,
        description="Optional language code hint (e.g. te, hi, en). When set, chunked decode skips per-chunk language detection.",
    ),
) -> JSONResponse:
    """
    Upload raw audio (webm/wav/mp3/…). Runs blocking Whisper in a thread pool.

    Response matches ``audio/demo`` ``/api/process`` for ``pipeline=chunked`` so the
    Pebble UI can use ``text_english`` for RAG and ``merged_text`` for display.
    """
    pl = pipeline.lower().strip()
    if pl == "chunked":
        _check_chunked_available()
        runner = _run_chunked_sync
    elif pl == "simple":
        _check_simple_available()
        runner = _run_simple_sync
    else:
        raise HTTPException(
            status_code=400,
            detail="pipeline must be 'chunked' or 'simple'",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty upload")

    suffix = Path(file.filename or "recording.webm").suffix
    if not suffix or len(suffix) > 8:
        suffix = ".webm"

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        try:
            if pl == "chunked":
                payload = await run_in_threadpool(
                    runner,
                    tmp_path,
                    model_size,
                    translate_model_size,
                    source_language_hint,
                )
            else:
                payload = await run_in_threadpool(runner, tmp_path, model_size)
        except FileNotFoundError as e:
            msg = str(e)
            if "ffmpeg" in msg.lower():
                raise HTTPException(
                    status_code=503,
                    detail="ffmpeg not found on PATH. macOS: brew install ffmpeg.",
                ) from e
            raise HTTPException(status_code=400, detail=msg) from e
        except Exception as e:
            logger.exception("Whisper pipeline failed")
            raise HTTPException(status_code=500, detail=str(e)) from e

        return JSONResponse(payload)
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
