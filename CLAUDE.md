# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A FastAPI + APScheduler HTTP-driven cron job scheduler. Clients create/delete/pause/resume jobs via REST API; each job fires an HTTP request on a cron schedule. Jobs are persisted in MongoDB (via APScheduler's MongoDBJobStore), so they survive restarts. Execution results are stored in a separate `job_runs` collection.

## Development

### Local (no Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Requires a reachable MongoDB — set MONGO_URI if not localhost
MONGO_URI=mongodb://localhost:27017 uvicorn app.main:app --reload --host 0.0.0.0 --port 8800
```

### Docker (recommended)

```bash
./tool.sh          # copies .env.example → .env if missing, then docker compose up -d --build + logs
# or manually:
cp .env.example .env
docker compose up -d --build
docker compose logs -f app
```

Service runs on port `8800`. MongoDB data persists in the `mongo_data` Docker volume.

## Architecture

All code lives in `app/`:

- **`config.py`** — reads env vars, exposes typed constants (`MONGO_URI`, `MONGO_DB`, `SCHEDULER_TZINFO`, `REQUEST_TIMEOUT`, etc.)
- **`main.py`** — the entire application: FastAPI app, APScheduler setup, MongoDB client, all Pydantic models, and all route handlers

The scheduler uses `AsyncIOScheduler` with `MongoDBJobStore` as its default jobstore — APScheduler serializes job definitions (kwargs) directly into MongoDB. A separate `runs_collection` stores each execution result written by `call_url_job`.

### Job lifecycle

1. `POST /jobs` validates the cron string (5-field standard or 6-field with seconds), adds job to `AsyncIOScheduler` with `coalesce=True, max_instances=1`.
2. APScheduler persists the job to MongoDB automatically.
3. At fire time, `call_url_job` sends an HTTP request via `httpx.AsyncClient` and writes a run record to `job_runs`.
4. `DELETE /jobs/{id}` calls `scheduler.remove_job()` — APScheduler also removes it from MongoDB.
5. Pause/resume set `next_run_time` to `None`/restored; status is derived from whether `next_run_time` is `None`.

### Key design choices

- Job status (`scheduled` / `paused`) is inferred at query time from `job.next_run_time is None` — not stored separately.
- MongoDB I/O in `list_job_runs` is wrapped with `asyncio.to_thread` since pymongo is synchronous.
- Duplicate job IDs return HTTP 409.
- No auth — designed for internal network use only.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MONGO_URI` | `mongodb://mongo:27017` | MongoDB connection string |
| `MONGO_DB` | `weizhi_crontask` | Database name |
| `JOBSTORE_COLLECTION` | `apscheduler_jobs` | APScheduler job store collection |
| `RUNS_COLLECTION` | `job_runs` | Execution history collection |
| `SCHEDULER_TZ` | `Asia/Shanghai` | Scheduler timezone |
| `REQUEST_TIMEOUT` | `10` | HTTP request timeout in seconds |
