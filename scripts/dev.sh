#!/usr/bin/env bash
# Local API server — same Supabase DB and .env as Render (pipeline updates production data).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON=""
for candidate in python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 \
    && "$candidate" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done
if [[ -z "$PYTHON" ]]; then
  echo "Need Python 3.11+. Install with: brew install python@3.12"
  exit 1
fi

if [[ ! -d .venv ]] || ! .venv/bin/python -c "import sys; exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
  echo "Creating .venv with $PYTHON …"
  rm -rf .venv
  "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q -r requirements.txt

# Same environment file as Render (DATABASE_URL, API keys, ADMIN_PASSWORD, …)
set -a
# shellcheck disable=SC1091
[[ -f .env ]] && source .env
set +a

export PORT="${PORT:-8000}"
export GIT_COMMIT="${GIT_COMMIT:-$(git rev-parse --short HEAD 2>/dev/null || echo local)}"
# Local dev: skip background seed + DB metric writes unless explicitly enabled in .env
export STARTUP_SEED="${STARTUP_SEED:-false}"
export PERSIST_OBSERVABILITY="${PERSIST_OBSERVABILITY:-false}"
export ENABLE_SCHEDULER="${ENABLE_SCHEDULER:-false}"

if [[ "${LOCAL_USE_SQLITE:-}" == "1" ]]; then
  export DATABASE_URL=
  echo "Mode: SQLite sandbox → data/football.db (NOT shared with Render)"
else
  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "ERROR: DATABASE_URL is not set in .env"
    echo "  Use the same Supabase URL as Render, or run with LOCAL_USE_SQLITE=1 for an isolated DB."
    exit 1
  fi
  echo "Mode: Supabase (shared with Render — pipeline & sync update production data)"
fi

if lsof -i ":${PORT}" -t >/dev/null 2>&1; then
  echo ""
  echo "ERROR: Port ${PORT} is already in use (another uvicorn/server is running)."
  echo "  • Stop it: Ctrl+C in that terminal, or run: kill \$(lsof -t -i :${PORT})"
  echo "  • Or use another port: PORT=8001 ./scripts/dev.sh"
  exit 1
fi

echo "Scheduler: ${ENABLE_SCHEDULER}  |  Startup seed: ${STARTUP_SEED}  |  DB metrics: ${PERSIST_OBSERVABILITY}"
echo "Tip: if pages are slow, a pipeline may be running on Render (shared Supabase). Check Monitor → Cancel."
echo "API:  http://127.0.0.1:${PORT}"
echo "UI:   http://127.0.0.1:${PORT}/#/monitor"
echo "Stop: Ctrl+C"
exec uvicorn api_server:app --reload --host 127.0.0.1 --port "$PORT"
