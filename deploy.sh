#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-tcloud}"
REMOTE_DIR="${REMOTE_DIR:-/home/weizhi-crontask}"

echo "deploying weizhi-crontask to ${REMOTE_HOST}:${REMOTE_DIR}"

ssh "$REMOTE_HOST" bash -s -- "$REMOTE_DIR" <<'REMOTE_SCRIPT'
set -euo pipefail

remote_dir="$1"
cd "$remote_dir"

echo "[1/5] pulling latest code"
git pull --ff-only

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "created ${remote_dir}/.env from .env.example; please edit MONGO_URI and rerun" >&2
  exit 1
fi

echo "[2/5] ensuring Docker network"
if ! docker network inspect rqk-net &>/dev/null; then
  docker network create rqk-net
fi

echo "[3/5] building image"
docker build -t weizhi-crontask:latest .

echo "[4/5] restarting container"
docker rm -f weizhi-crontask 2>/dev/null || true
docker run -d \
  -p 8800:8800 \
  --restart always \
  --env-file .env \
  --name weizhi-crontask \
  --network rqk-net \
  weizhi-crontask:latest

echo "[5/5] checking health"
health_url="http://127.0.0.1:8800/health"
for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error "$health_url" >/dev/null 2>&1; then
    echo "weizhi-crontask deployed successfully: ${health_url}"
    docker ps --filter name=^/weizhi-crontask$ --format 'container={{.Names}} status={{.Status}}'
    exit 0
  fi
  sleep 1
done

echo "weizhi-crontask failed health check: ${health_url}" >&2
docker logs --tail 100 weizhi-crontask >&2 || true
exit 1
REMOTE_SCRIPT
