#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRJ="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONT="$PRJ/frontend"

echo "=== Frontend (Vite + React) @ http://localhost:5173 ==="
echo "    API base: \${VITE_API_BASE_URL:-http://localhost:8001} (brain: /generate-answer, /audio/transcribe)"
cd "$FRONT"

if [[ ! -d node_modules ]]; then
  echo "Installing pnpm dependencies (first run)..."
  pnpm install
fi

exec pnpm dev
