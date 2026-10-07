"""Run: python -m audio <file> (from the parent of the ``audio`` package directory)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Transcribe audio with Whisper; prints detected language and text.",
    )
    parser.add_argument(
        "audio_path",
        type=Path,
        help="Path to audio file (wav, mp3, flac, …).",
    )
    parser.add_argument(
        "--model",
        default="base",
        help="Whisper model: tiny, base, small, medium, large, turbo, …",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Optional: force language (Whisper name, e.g. Japanese).",
    )
    parser.add_argument(
        "--translate",
        action="store_true",
        help="Translate speech to English; prints source language and English text.",
    )
    args = parser.parse_args()

    from audio.transcribe import transcribe_file, translate_speech_to_english

    try:
        if args.translate:
            model = args.model
            if model == "base":
                model = "medium"
            out = translate_speech_to_english(
                args.audio_path,
                model_size=model,
                source_language=args.language,
            )
        else:
            out = transcribe_file(
                args.audio_path,
                model_size=args.model,
                language=args.language,
            )
    except ImportError as e:
        print(e, file=sys.stderr)
        return 1

    if args.translate:
        label = (out.source_language_name or "").title() if out.source_language_name else ""
        if label:
            print(f"source_language: {out.source_language} ({label})")
        else:
            print(f"source_language: {out.source_language}")
        print(out.text_english)
    else:
        label = out.language_name or ""
        if label:
            print(f"language: {out.language} ({label})")
        else:
            print(f"language: {out.language}")
        print(out.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
