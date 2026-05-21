#!/usr/bin/env bash
set -euo pipefail

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "created .env from .env.example"
fi

docker compose up -d --build
docker compose logs -f app
