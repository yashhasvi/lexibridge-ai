#!/usr/bin/env python3
"""
CLI: microphone (record) → chunked Whisper (audio) → Brain /ask.

Uses the same stack as the Pebble web UI's server-side path:
  record.record_to_file → audio.transcribe_chunked → httpx POST /ask

Run from repo root with venv activated:
  python scripts/cli_voice_query.py --duration 8

Requires: PortAudio + ffmpeg + openai-whisper + pydub (see record/ and audio/requirements.txt).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Record mic → Whisper → Brain Q&A")
    p.add_argument("--duration", type=float, default=6.0, help="Seconds to record")
    p.add_argument(
        "--brain",
        default="http://127.0.0.1:8001",
        help="Brain API base URL",
    )
    p.add_argument(
        "--model",
        default="base",
        help="Whisper model size (tiny, base, small, …)",
    )
    p.add_argument(
        "--device",
        type=int,
        default=None,
        help="sounddevice input device index (default: system default)",
    )
    args = p.parse_args()

    try:
        import httpx
    except ImportError:
        print("Install httpx in the project venv.", file=sys.stderr)
        return 1

    out = REPO_ROOT / ".cache" / "cli_last_query.wav"
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        from record import record_to_file
    except ImportError as e:
        print(e, file=sys.stderr)
        return 1

    print(f"Recording {args.duration:.1f}s to {out} …", flush=True)
    try:
        record_to_file(
            out,
            duration=args.duration,
            device=args.device,
            show_level=True,
        )
    except Exception as e:
        print(f"Recording failed: {e}", file=sys.stderr)
        return 1

    try:
        from audio.chunk import transcribe_chunked
    except ImportError as e:
        print(e, file=sys.stderr)
        return 1

    print("Running silence-split Whisper pipeline…", flush=True)
    try:
        tr = transcribe_chunked(str(out), model_size=args.model)
    except Exception as e:
        print(f"Transcription failed: {e}", file=sys.stderr)
        return 1

    question = (tr.text_english or tr.merged_text or "").strip()
    if not question:
        print("No speech detected.", file=sys.stderr)
        return 1

    print(f"\nQuestion (English, for RAG): {question}\n", flush=True)
    if tr.is_multilingual:
        langs = ", ".join(tr.languages_detected)
        print(f"(Multilingual audio; languages seen: {langs})\n", flush=True)
        for c in tr.chunks:
            label = c.language_name or c.language
            print(f"  [{c.start_label}→{c.end_label}] ({label}) {c.text}")

    url = f"{args.brain.rstrip('/')}/ask"
    try:
        r = httpx.post(url, json={"question": question}, timeout=300.0)
    except httpx.RequestError as e:
        print(f"Brain request failed: {e}", file=sys.stderr)
        return 1

    if not r.is_success:
        print(r.text, file=sys.stderr)
        return 1

    data = r.json()
    print("--- Answer ---\n")
    print(data.get("answer", json.dumps(data, indent=2)))
    print("\n--- Sources (first 5) ---")
    for s in (data.get("sources") or [])[:5]:
        print(f"  [{s.get('citation_index')}] {s.get('source_name')}  {s.get('url', '')[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
