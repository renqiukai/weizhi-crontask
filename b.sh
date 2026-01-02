#!/usr/bin/env bash
set -euo pipefail

export ENV=development

if [ -f ".env" ]; then
  set -a
  . ./.env.dev
  set +a
fi

if [ -f ".venv/bin/activate" ]; then
  . ./.venv/bin/activate
  pip install -r requirements.txt
fi

uvicorn app.main:app --reload --host 0.0.0.0 --port 8800
