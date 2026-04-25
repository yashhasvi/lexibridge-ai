"""
Silence-split → per-chunk language detection → explicit-language transcription pipeline.

Why this beats one-shot Whisper on mixed-language audio:
- Whisper can "lock onto" the wrong language after the first window and drift for the
  rest of the file. Splitting on silence keeps each chunk short and mostly monolingual.
- Feeding the detected language code back as ``language=`` prevents the decoder from
  second-guessing itself mid-segment.

Pipeline
--------
1. Load audio with pydub (any format ffmpeg supports).
2. ``detect_nonsilent()`` → list of (start_ms, end_ms) speech regions.
3. Pad each region with a bit of silence context, merge overlaps.
4. Per chunk: ``whisper.detect_language()`` → ``model.transcribe(language=lang)``.
5. Merge chunk texts.
6. One translate pass on the full audio for the English version.
"""

from __future__ import annotations

import logging
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

try:
    from pydub import AudioSegment
    from pydub.silence import detect_nonsilent

    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logger.debug("pydub not installed; chunked transcription unavailable.")


@dataclass
class ChunkResult:
    """Transcription result for one silence-bounded audio segment."""

    index: int
    start_ms: int
    end_ms: int
    language: str
    """Whisper language code (e.g. ``en``, ``ja``)."""
    language_name: Optional[str]
    text: str

    @property
    def duration_s(self) -> float:
        return (self.end_ms - self.start_ms) / 1000.0

    @property
    def start_label(self) -> str:
        return _ms_label(self.start_ms)

    @property
    def end_label(self) -> str:
        return _ms_label(self.end_ms)


@dataclass
class ChunkedTranscriptionResult:
    """Output of the full chunked pipeline."""

    chunks: list[ChunkResult]
    """Per-segment transcripts in order."""
    merged_text: str
    """All chunk texts joined with spaces."""
    text_english: str
    """Full-audio Whisper translate pass (English)."""
    languages_detected: list[str]
    """Unique language codes in order of first appearance."""
    source_language: str
    """Most-frequent language across all chunks."""
    source_language_name: Optional[str]

    @property
    def is_multilingual(self) -> bool:
        return len(self.languages_detected) > 1


def _ms_label(ms: int) -> str:
    s, _ = divmod(ms, 1000)
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


def transcribe_chunked(
    audio_path: Union[str, Path],
    *,
    model_size: str = "base",
    translate_model_size: Optional[str] = None,
    device: Optional[str] = None,
    source_language_hint: Optional[str] = None,
    min_silence_len: int = 700,
    silence_thresh: int = -40,
    keep_silence: int = 200,
    min_chunk_ms: int = 400,
    **transcribe_options: Any,
) -> ChunkedTranscriptionResult:
    """
    Split on silence, detect language per chunk, transcribe each with explicit language.

    Parameters
    ----------
    audio_path:
        Any audio file format supported by ffmpeg (wav, mp3, webm, flac, …).
    model_size:
        Whisper model id for per-chunk transcription. ``base`` is fast;
        ``small``/``medium`` are more accurate.
    translate_model_size:
        Optional Whisper model id for the final full-audio English translate pass.
        If omitted, uses ``small`` when ``model_size`` is ``tiny``/``base``, else
        reuses ``model_size``.
    device:
        ``cuda``, ``cpu``, or ``None`` for PyTorch default.
    source_language_hint:
        Optional Whisper language code (e.g. ``te``). When set, chunk language
        detection is skipped and all chunks are decoded using this language.
    min_silence_len:
        Minimum continuous silence (ms) that counts as a split point.
    silence_thresh:
        dBFS level below which audio is considered silent.  Lower (more negative) =
        only split on very quiet gaps. Raise towards -30 for noisy environments.
    keep_silence:
        Milliseconds of silence to keep at the edges of each chunk so Whisper has
        a natural-sounding start/end.
    min_chunk_ms:
        Skip chunks shorter than this (noise, breaths, etc.).
    transcribe_options:
        Extra kwargs forwarded to ``model.transcribe()`` (e.g. ``fp16=False``).
    """
    if not PYDUB_AVAILABLE:
        raise ImportError(
            "pydub is required for chunked transcription. "
            "Install with: pip install pydub  (ffmpeg must be on PATH)"
        )

    # Local imports avoid circular deps and let the module load without whisper.
    from audio.transcribe import (
        _ensure_ffmpeg_on_path,
        _get_model,
        _language_name,
        translate_speech_to_english,
    )

    _ensure_ffmpeg_on_path()

    path = Path(audio_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")

    audio = AudioSegment.from_file(str(path))

    # ── 1. Find non-silent regions ──────────────────────────────────────────
    raw_ranges: list[tuple[int, int]] = detect_nonsilent(
        audio,
        min_silence_len=min_silence_len,
        silence_thresh=silence_thresh,
        seek_step=10,
    )
    if not raw_ranges:
        logger.warning("No speech detected; treating full audio as one chunk.")
        raw_ranges = [(0, len(audio))]

    # ── 2. Pad + merge overlapping ranges ───────────────────────────────────
    padded = [
        (max(0, s - keep_silence), min(len(audio), e + keep_silence))
        for s, e in raw_ranges
    ]
    merged_ranges: list[tuple[int, int]] = []
    for s, e in sorted(padded):
        if merged_ranges and s <= merged_ranges[-1][1]:
            merged_ranges[-1] = (merged_ranges[-1][0], max(merged_ranges[-1][1], e))
        else:
            merged_ranges.append((s, e))

    # ── 3. Load model once ──────────────────────────────────────────────────
    model = _get_model(model_size, device=device)

    import whisper as _whisper  # noqa: PLC0415

    opts = dict(transcribe_options)
    # fp16 makes no sense on CPU; auto-disable
    try:
        import torch

        if not torch.cuda.is_available():
            opts.setdefault("fp16", False)
    except ImportError:
        opts.setdefault("fp16", False)

    # ── 4. Per-chunk: detect language → transcribe ──────────────────────────
    chunk_results: list[ChunkResult] = []
    for i, (start_ms, end_ms) in enumerate(merged_ranges):
        chunk = audio[start_ms:end_ms]
        if len(chunk) < min_chunk_ms:
            logger.debug("Skipping chunk %d (%d ms, too short)", i, len(chunk))
            continue

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            chunk.export(tmp.name, format="wav")
            tmp_path = tmp.name

        try:
            if source_language_hint:
                lang_code = source_language_hint.strip().lower()
            else:
                arr = _whisper.load_audio(tmp_path)
                arr = _whisper.pad_or_trim(arr)
                mel = _whisper.log_mel_spectrogram(
                    arr, n_mels=model.dims.n_mels
                ).to(model.device)
                _, probs = model.detect_language(mel)
                lang_code = max(probs, key=probs.get)

            result = model.transcribe(
                tmp_path,
                language=lang_code,
                task="transcribe",
                **opts,
            )
            text = (result.get("text") or "").strip()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        chunk_results.append(
            ChunkResult(
                index=len(chunk_results),
                start_ms=start_ms,
                end_ms=end_ms,
                language=lang_code,
                language_name=_language_name(lang_code),
                text=text,
            )
        )
        logger.debug(
            "Chunk %d [%s→%s] lang=%s: %.80s",
            chunk_results[-1].index,
            _ms_label(start_ms),
            _ms_label(end_ms),
            lang_code,
            text,
        )

    # ── 5. Merge + language summary ──────────────────────────────────────────
    merged_text = " ".join(c.text for c in chunk_results if c.text)
    seen: dict[str, None] = {}
    for c in chunk_results:
        seen.setdefault(c.language, None)
    languages_detected = list(seen)

    counts = Counter(c.language for c in chunk_results)
    if source_language_hint:
        dominant = source_language_hint.strip().lower()
    else:
        dominant = counts.most_common(1)[0][0] if counts else "unknown"

    # ── 6. Full-audio translate pass (English) ──────────────────────────────
    effective_translate_model = (
        translate_model_size
        or ("small" if model_size in {"tiny", "base"} else model_size)
    )
    eng = translate_speech_to_english(
        path,
        model_size=effective_translate_model,
        device=device,
        source_language=dominant if dominant != "unknown" else None,
        **opts,
    )

    return ChunkedTranscriptionResult(
        chunks=chunk_results,
        merged_text=merged_text,
        text_english=eng.text_english,
        languages_detected=languages_detected,
        source_language=dominant,
        source_language_name=_language_name(dominant),
    )
