#!/usr/bin/env bash
# One command to set up and start the explorer on macOS or Linux.
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8000}"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi
[ -f data/claims_enriched.csv.gz ] || .venv/bin/python -m app.pipeline
echo "Open http://localhost:${PORT}"
exec .venv/bin/uvicorn app.main:app --port "${PORT}"
