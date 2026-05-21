#!/usr/bin/env bash
set -euo pipefail

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "created .env from .env.example, please edit MONGO_URI before rerunning"
  exit 1
fi

if ! docker network inspect rqk-net &>/dev/null; then
  docker network create rqk-net
  echo "created docker network: rqk-net"
fi

docker build -t weizhi-crontask:latest .
docker rm -f weizhi-crontask 2>/dev/null || true
docker run -d \
  -p 8800:8800 \
  --restart always \
  --env-file .env \
  --name weizhi-crontask \
  --network rqk-net \
  weizhi-crontask:latest
docker logs -f weizhi-crontask
