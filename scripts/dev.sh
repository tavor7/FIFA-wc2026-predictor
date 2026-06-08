#!/usr/bin/env bash
# Local dev server — fast iteration without Render deploys.
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

# Load .env then override for local-friendly defaults
set -a
# shellcheck disable=SC1091
[[ -f .env ]] && source .env
set +a

export ENABLE_SCHEDULER="${ENABLE_SCHEDULER:-false}"
export STARTUP_SEED="${STARTUP_SEED:-true}"
export PORT="${PORT:-8000}"

# Default: SQLite in data/football.db (fast, isolated from production).
# To use your Supabase DB locally instead: LOCAL_USE_SUPABASE=1 ./scripts/dev.sh
if [[ "${LOCAL_USE_SUPABASE:-}" != "1" ]]; then
  export DATABASE_URL=
  echo "Local DB: SQLite → data/football.db"
else
  echo "Local DB: Supabase (DATABASE_URL from .env)"
fi

echo "API:  http://127.0.0.1:${PORT}"
echo "UI:   http://127.0.0.1:${PORT}/#/monitor"
echo "Stop: Ctrl+C"
exec uvicorn api_server:app --reload --host 127.0.0.1 --port "$PORT"
