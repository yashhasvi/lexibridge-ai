#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRJ="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== LightRAG server @ :9621 ==="
cd "$PRJ/brain_module"
# Optional env for lightrag-server (LLM_BINDING_HOST, etc.)
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env || echo "warning: could not source brain_module/.env (TCC). Grant iTerm Full Disk Access or move the repo off Desktop." >&2
  set +a
fi
# LightRAG reads EMBEDDING_MODEL directly; override so it uses the Ollama
# model rather than the HuggingFace model set for data_module.
export EMBEDDING_MODEL="${LIGHTRAG_EMBEDDING_MODEL:-nomic-embed-text}"

exec uv run --project "$PRJ/brain_module" --python 3.10 lightrag-server --host 0.0.0.0 --port 9621 --working-dir "$PRJ/lightrag_data"
