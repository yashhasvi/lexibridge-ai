#!/usr/bin/env bash
# start_services.sh — open a dedicated Terminal window for every service
# Usage: bash start_services.sh [--iterm]   (use --iterm for iTerm2 split panes)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRJ="$SCRIPT_DIR"

# Python services run via scripts/run_*.sh (venv activate + correct cwd). A *single*
# `bash /path/to/script` line is sent to Terminal/iTerm so AppleScript does not
# split a long inline command and drop PYTHONPATH / break temp paths.

# ── helpers ──────────────────────────────────────────────────────────────────
# Commands are written to a temp script so we never embed multi-line strings
# (with newlines, 'set', 'source', etc.) directly inside AppleScript literals.

_make_tmp() {       # _make_tmp <cmd>  → prints path to temp script
  local tmp
  tmp=$(mktemp -t svc_launch)   # macOS: Xs must be at end; -t handles that
  printf '#!/usr/bin/env bash\n%s\n' "$1" > "$tmp"
  chmod +x "$tmp"
  echo "$tmp"
}

open_terminal() {
  local title="$1"
  local tmp
  tmp=$(_make_tmp "$2")
  osascript - "$title" "$tmp" <<'APPLESCRIPT' >/dev/null
on run {wtitle, wscript}
  tell application "Terminal"
    activate
    set w to do script ("bash " & wscript)
    set custom title of (front window) to wtitle
  end tell
end run
APPLESCRIPT
}

open_iterm() {
  local tmp
  tmp=$(_make_tmp "$2")
  # Use "iTerm" (not "iTerm2") for AppleScript. Prefer new window + write text:
  # `create window … command …` often returns "missing value" and can fail to run long-lived servers reliably.
  osascript - "$tmp" <<'APPLESCRIPT' >/dev/null
on run {wscript}
  tell application "iTerm"
    activate
    set w to (create window with default profile)
    tell current session of w
      write text ("bash " & quoted form of wscript)
    end tell
  end tell
end run
APPLESCRIPT
}

USE_ITERM=false
[[ "${1:-}" == "--iterm" ]] && USE_ITERM=true

launch() {          # launch <title> <shell-command>
  local title="$1"
  local cmd="$2"
  if $USE_ITERM; then
    open_iterm "$title" "$cmd"
  else
    open_terminal "$title" "$cmd"
  fi
  sleep 0.4         # brief pause so windows don't stack instantly
}

# Poll LightRAG until GET /health returns 200 (same check as brain_module LightRAGClient.health).
# Override: LIGHTRAG_HEALTH_URL, LIGHTRAG_WAIT_MAX_ATTEMPTS, LIGHTRAG_WAIT_INTERVAL_SEC
wait_for_lightrag_ready() {
  local url="${LIGHTRAG_HEALTH_URL:-http://127.0.0.1:9621/health}"
  local max_attempts="${LIGHTRAG_WAIT_MAX_ATTEMPTS:-120}"
  local interval="${LIGHTRAG_WAIT_INTERVAL_SEC:-2}"
  local attempt=0
  echo ""
  echo "⏳  Waiting for LightRAG to be ready (${url}) …"
  while (( attempt < max_attempts )); do
    if curl -sf --max-time 5 "$url" >/dev/null 2>&1; then
      echo "✓  LightRAG is ready (GET /health OK)."
      return 0
    fi
    attempt=$((attempt + 1))
    if (( attempt % 15 == 0 )); then
      echo "   … still waiting (${attempt}/${max_attempts} checks, ~$((attempt * interval))s elapsed)"
    fi
    sleep "$interval"
  done
  echo "✗  Timed out waiting for LightRAG at ${url} after ~$((max_attempts * interval))s." >&2
  echo "   Fix the LightRAG window errors, or raise LIGHTRAG_WAIT_MAX_ATTEMPTS / interval." >&2
  return 1
}

# ── 1. Neo4j ─────────────────────────────────────────────────────────────────
# Graph DB for fast knowledge-graph traversals (replaces slow NetworkX pickle).
launch "Neo4j :7687" \
  "echo '=== Neo4j Graph DB @ :7687 (browser :7474) ===' && if lsof -nP -iTCP:7687 -sTCP:LISTEN >/dev/null 2>&1; then echo 'Port 7687 already in use — Neo4j is probably already running.'; exec \"\$SHELL\" -l; else neo4j console; fi"

# ── 2. Ollama ────────────────────────────────────────────────────────────────
# Skip if :11434 already listening (re-running the script would otherwise error).
launch "Ollama" \
  "echo '=== Ollama (LLM + Embeddings @ :11434) ===' && if lsof -nP -iTCP:11434 -sTCP:LISTEN >/dev/null 2>&1; then echo 'Port 11434 already in use — Ollama is probably already running.'; exec \"\$SHELL\" -l; else ollama serve; fi"

# ── 3. Redis ─────────────────────────────────────────────────────────────────
# Skip if :6379 already listening (common after a previous start_services run).
launch "Redis" \
  "echo '=== Redis cache @ :6379 ===' && if lsof -nP -iTCP:6379 -sTCP:LISTEN >/dev/null 2>&1; then echo 'Port 6379 already in use — Redis is probably already running.'; exec \"\$SHELL\" -l; else redis-server; fi"

# ── 4. LightRAG server ───────────────────────────────────────────────────────
launch "LightRAG" "bash \"$PRJ/scripts/run_lightrag.sh\""
wait_for_lightrag_ready

# ── 5. FastRAG / Brain Module (FastAPI) ──────────────────────────────────────
launch "Brain Module :8001" "bash \"$PRJ/scripts/run_brain_module.sh\""

# ── 6. Frontend (Vite dev server) ────────────────────────────────────────────
launch "Frontend :5173" "bash \"$PRJ/scripts/run_frontend.sh\""

echo ""
echo "✅  All service windows opened."
echo ""
echo "   Port map:"
echo "   :7687   Neo4j           (graph DB — browser at :7474)"
echo "   :11434  Ollama          (LLM + Embeddings)"
echo "   :6379   Redis           (query cache)"
echo "   :9621   LightRAG        (graph RAG server)"
echo "   :8001   Brain Module    (RAG + /audio/transcribe Whisper when whisper+pydub installed)"
echo "   :5173   Frontend        (Vite + React UI)"
echo ""
echo "   If you still see PermissionError on paths under Desktop: grant iTerm (or Terminal)"
echo "   Full Disk Access in System Settings → Privacy & Security, or move the repo off Desktop."
