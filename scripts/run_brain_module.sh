#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRJ="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Brain Module (FastRAG | Hybrid | GraphRAG | LightRAG) @ :8001 ==="
echo "    PYTHONPATH includes repo root + data_module package root"
export PYTHONPATH="$PRJ/data_module:$PRJ${PYTHONPATH:+:$PYTHONPATH}"

if [[ "${BRAIN_AUDIO_BOOTSTRAP:-1}" == "1" ]]; then
  echo "    Checking optional audio deps (whisper, pydub, edge-tts) ..."
  uv sync --project "$PRJ/brain_module" --python 3.10 --extra audio >/dev/null
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ERROR: ffmpeg not found on PATH." >&2
  echo "Install it (macOS): brew install ffmpeg" >&2
  exit 1
fi

if [[ "${BRAIN_DEV_RELOAD:-1}" == "1" ]]; then
  exec uv run --project "$PRJ/brain_module" --python 3.10 uvicorn brain_module.api.main:app --host 0.0.0.0 --port 8001 --reload
fi
exec uv run --project "$PRJ/brain_module" --python 3.10 uvicorn brain_module.api.main:app --host 0.0.0.0 --port 8001
