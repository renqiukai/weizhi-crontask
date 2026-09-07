# Repository Guidelines

## Project Structure

This is a small FastAPI service that schedules HTTP calls with APScheduler and
persists jobs and execution history in MongoDB.

- `app/main.py` contains the application lifespan, scheduler setup, Pydantic
  request/response models, and all API routes.
- `app/config.py` reads and validates environment-backed configuration.
- `requirements.txt` lists runtime dependencies; `Dockerfile` builds the
  production image.
- `b.sh` starts local development and optionally loads `.env.dev`; `tool.sh`
  builds and runs the Docker container. `readme.md` documents the public API.

Keep new application code under `app/`. Add tests under `tests/` using the same
module-oriented names, for example `tests/test_jobs.py`.

## Build, Test, and Development Commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # install runtime dependencies
MONGO_URI=mongodb://localhost:27017 uvicorn app.main:app --reload --host 0.0.0.0 --port 8800
./b.sh                                   # local server; loads .env.dev when present
./tool.sh                                # build and run Docker on port 8800
curl http://localhost:8800/health        # basic service check
```

MongoDB must be reachable before starting the app. Do not commit `.env` or
`.env.dev`; use the example configuration as the starting point.

## Coding Style and API Conventions

Use Python 3.10+ syntax, four-space indentation, type annotations, and
`snake_case` for functions, variables, and modules. Keep Pydantic models close
to the routes that use them. Route handlers should return declared response
models and use `HTTPException` for client-facing validation errors. Preserve
the existing async boundary: wrap synchronous PyMongo work with
`asyncio.to_thread` rather than blocking the event loop.

Job IDs are client-provided strings (for example, `job-ping-001`). Preserve the
existing five- or six-field cron support, upper-case HTTP methods, and the
`scheduled`/`paused` status semantics.

## Testing Guidelines

There is currently no committed test suite or configured formatter/linter. Add
pytest tests for changed behavior, especially invalid cron input, duplicate or
missing jobs, pause/resume state, and execution-record persistence. Run the
relevant tests with `pytest`; at minimum, verify `/health` against a running
service and exercise changed endpoints with `curl`.

## Commits and Pull Requests

Recent commits use short imperative Chinese summaries, often naming the affected
API or deployment behavior, e.g. `修复 PATCH 接口 500 错误`. Keep commits scoped
to one change. Pull requests should explain the behavior change, list test or
manual verification evidence, note MongoDB/configuration implications, and
include request/response examples for API changes. Never expose credentials,
internal URLs, or production data in diffs, logs, or screenshots.
