"""
CLI entry point:  python -m record [output.wav] [options]

Examples
--------
    # Record until Ctrl-C → save to recording.wav
    python -m record

    # Record for 10 seconds → save to clip.wav
    python -m record clip.wav --duration 10

    # List available audio devices then exit
    python -m record --list-devices

    # Record + immediately transcribe (requires audio module)
    python -m record session.wav --transcribe
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_OUTPUT = "recordings/recording.wav"


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m record",
        description="Record from the system microphone and save to a WAV file.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path(DEFAULT_OUTPUT),
        help=f"Output file path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--duration", "-d",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Record for this many seconds (default: record until Ctrl-C)",
    )
    parser.add_argument(
        "--samplerate", "-r",
        type=int,
        default=16_000,
        help="Sample rate in Hz (default: 16000 — Whisper's native rate)",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Input device name or index (default: system default)",
    )
    parser.add_argument(
        "--no-level",
        action="store_true",
        help="Suppress the live RMS level bar",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Print available audio devices and exit",
    )
    parser.add_argument(
        "--transcribe",
        action="store_true",
        help="Run the audio module's chunked transcription after recording",
    )
    args = parser.parse_args()

    if args.list_devices:
        try:
            from record import list_devices
            list_devices()
        except ImportError as e:
            print(e, file=sys.stderr)
            return 1
        return 0

    try:
        from record import record_to_file
    except ImportError as e:
        print(e, file=sys.stderr)
        return 1

    try:
        saved = record_to_file(
            args.output,
            duration=args.duration,
            samplerate=args.samplerate,
            device=args.device,
            show_level=not args.no_level,
        )
    except Exception as e:
        print(f"Recording failed: {e}", file=sys.stderr)
        return 1

    if args.transcribe:
        print("\nRunning transcription…", flush=True)
        try:
            from audio import transcribe_chunked
        except ImportError:
            print(
                "audio module not importable. Make sure you run from the repo root "
                "and that openai-whisper + pydub are installed.",
                file=sys.stderr,
            )
            return 1
        result = transcribe_chunked(saved)
        langs = ", ".join(result.languages_detected)
        print(f"\nlanguages : {langs}")
        if result.is_multilingual:
            for c in result.chunks:
                label = c.language_name or c.language
                print(f"  [{c.start_label}→{c.end_label}] ({label})  {c.text}")
        print(f"\noriginal  : {result.merged_text}")
        print(f"english   : {result.text_english}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
