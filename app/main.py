import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import AnyHttpUrl, BaseModel, Field
from pymongo import MongoClient

from app.config import (
    JOBSTORE_COLLECTION,
    MONGO_DB,
    MONGO_URI,
    REQUEST_TIMEOUT,
    RUNS_COLLECTION,
    SCHEDULER_TZINFO,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduler.start()
    logger.info("scheduler started")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        mongo_client.close()
        logger.info("scheduler stopped")


app = FastAPI(title="Weizhi Crontask", lifespan=lifespan)

jobstores = {
    "default": MongoDBJobStore(
        database=MONGO_DB,
        collection=JOBSTORE_COLLECTION,
        host=MONGO_URI,
    )
}

scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=SCHEDULER_TZINFO)
mongo_client = MongoClient(MONGO_URI)
runs_collection = mongo_client[MONGO_DB][RUNS_COLLECTION]


async def _insert_run_record(record: dict) -> None:
    await asyncio.to_thread(runs_collection.insert_one, record)


async def call_url_job(
    url: str,
    method: str = "GET",
    job_id: str | None = None,
    _cron: str | None = None,
    headers: dict[str, str] | None = None,
    body: str | None = None,
) -> None:
    run_at = datetime.now(tz=timezone.utc)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.request(method, url, headers=headers, content=body)
            record = {
                "job_id": job_id or "unknown",
                "url": url,
                "cron": _cron,
                "method": method,
                "status_code": response.status_code,
                "ok": response.status_code < 400,
                "response_text": response.text,
                "elapsed_ms": response.elapsed.total_seconds() * 1000,
                "error": None,
                "run_at": run_at,
            }
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.warning("job call failed url={} err={}", url, exc)
            record = {
                "job_id": job_id or "unknown",
                "url": url,
                "cron": _cron,
                "method": method,
                "status_code": None,
                "ok": False,
                "response_text": None,
                "elapsed_ms": None,
                "error": str(exc),
                "run_at": run_at,
            }
    await _insert_run_record(record)


class JobCreate(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    cron: str
    url: AnyHttpUrl
    method: str = "GET"
    headers: dict[str, str] | None = None
    body: str | None = None


class JobInfo(BaseModel):
    id: str
    cron: str
    url: AnyHttpUrl
    method: str
    headers: dict[str, str] | None
    body: str | None
    next_run_time: datetime | None
    status: str


class JobResult(BaseModel):
    id: str
    status: str


class JobRun(BaseModel):
    job_id: str
    url: AnyHttpUrl
    cron: str | None
    method: str
    status_code: int | None
    ok: bool
    response_text: str | None
    elapsed_ms: float | None
    error: str | None
    run_at: datetime


class JobRunList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[JobRun]


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/jobs", response_model=JobResult)
async def create_job(payload: JobCreate) -> JobResult:
    if scheduler.get_job(payload.id):
        raise HTTPException(status_code=409, detail="job id already exists")
    method = payload.method.upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise HTTPException(
            status_code=400, detail="method must be GET/POST/PUT/PATCH/DELETE"
        )
    try:
        cron_parts = payload.cron.split()
        if len(cron_parts) == 5:
            trigger = CronTrigger.from_crontab(payload.cron, timezone=SCHEDULER_TZINFO)
        elif len(cron_parts) == 6:
            second, minute, hour, day, month, day_of_week = cron_parts
            trigger = CronTrigger(
                second=second,
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
                timezone=SCHEDULER_TZINFO,
            )
        else:
            raise ValueError("cron must have 5 or 6 fields")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    scheduler.add_job(
        call_url_job,
        trigger=trigger,
        id=payload.id,
        kwargs={
            "url": str(payload.url),
            "method": method,
            "job_id": payload.id,
            "_cron": payload.cron,
            "headers": payload.headers,
            "body": payload.body,
        },
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    return JobResult(id=payload.id, status="scheduled")


@app.get("/jobs/{job_id}", response_model=JobInfo)
async def get_job(job_id: str) -> JobInfo:
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    url = job.kwargs.get("url")
    cron = job.kwargs.get("_cron")
    method = job.kwargs.get("method", "GET")
    headers = job.kwargs.get("headers")
    body = job.kwargs.get("body")
    status = "paused" if job.next_run_time is None else "scheduled"
    return JobInfo(
        id=job.id,
        cron=cron,
        url=url,
        method=method,
        headers=headers,
        body=body,
        next_run_time=job.next_run_time,
        status=status,
    )


@app.delete("/jobs/{job_id}", response_model=JobResult)
async def delete_job(job_id: str) -> JobResult:
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    scheduler.remove_job(job_id)
    return JobResult(id=job_id, status="deleted")


@app.post("/jobs/{job_id}/pause", response_model=JobResult)
async def pause_job(job_id: str) -> JobResult:
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    scheduler.pause_job(job_id)
    return JobResult(id=job_id, status="paused")


@app.post("/jobs/{job_id}/resume", response_model=JobResult)
async def resume_job(job_id: str) -> JobResult:
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    scheduler.resume_job(job_id)
    return JobResult(id=job_id, status="scheduled")


@app.get("/jobs/{job_id}/runs", response_model=JobRunList)
async def list_job_runs(job_id: str, limit: int = 20, offset: int = 0) -> JobRunList:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be 1-200")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")
    query = {"job_id": job_id}

    def _fetch() -> tuple[int, list[dict]]:
        total = runs_collection.count_documents(query)
        cursor = (
            runs_collection.find(query).sort("run_at", -1).skip(offset).limit(limit)
        )
        items = []
        for doc in cursor:
            doc.pop("_id", None)
            items.append(doc)
        return total, items

    total, items = await asyncio.to_thread(_fetch)
    return JobRunList(total=total, limit=limit, offset=offset, items=items)
