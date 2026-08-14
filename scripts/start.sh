#!/usr/bin/env bash
# One-click source deployment: venv, deps, .env, then listen on port 1921.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

mkdir -p data

if [[ ! -f .env ]]; then
  SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
  sed "s/^SECRET_KEY=.*/SECRET_KEY=${SECRET}/" .env.example > .env
  echo "Created .env with a generated SECRET_KEY"
fi

PORT_VALUE="$(grep -E '^PORT=' .env | tail -n 1 | cut -d= -f2- || true)"
export PORT="${PORT_VALUE:-1921}"
export FLASK_APP=run.py

if [[ "${PROD:-0}" == "1" ]]; then
  WORKERS="$(grep -E '^GUNICORN_WORKERS=' .env | tail -n 1 | cut -d= -f2- || true)"
  TIMEOUT="$(grep -E '^GUNICORN_TIMEOUT=' .env | tail -n 1 | cut -d= -f2- || true)"
  exec gunicorn --workers "${WORKERS:-1}" --bind "0.0.0.0:${PORT}" --timeout "${TIMEOUT:-600}" wsgi:app
fi

echo "VerifyLite listening on http://0.0.0.0:${PORT}"
exec python run.py
