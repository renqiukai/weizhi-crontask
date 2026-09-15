import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

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
    CALLBACK_BASE_URL,
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


async def _update_run_record(
    run_id: str, values: dict, statuses: list[str] | None = None
) -> None:
    query = {"run_id": run_id}
    if statuses:
        query["status"] = {"$in": statuses}
    await asyncio.to_thread(
        runs_collection.update_one,
        query,
        {"$set": values},
    )


async def call_url_job(
    url: str,
    method: str = "GET",
    job_id: str | None = None,
    _cron: str | None = None,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    _remark: str | None = None,
    _await_callback: bool = False,
) -> None:
    run_id = uuid.uuid4().hex
    run_at = datetime.now(tz=timezone.utc)
    await_callback = bool(_await_callback)
    await _insert_run_record(
        {
            "job_id": job_id or "unknown",
            "run_id": run_id,
            "url": url,
            "cron": _cron,
            "method": method,
            "status": "running",
            "status_code": None,
            "ok": None,
            "response_text": None,
            "elapsed_ms": None,
            "error": None,
            "run_at": run_at,
            "completed_at": None,
        }
    )
    request_headers = dict(headers or {})
    if await_callback:
        callback_url = f"{CALLBACK_BASE_URL.rstrip('/')}/runs/{run_id}/complete"
        request_headers.update(
            {
                "X-Task-Run-Id": run_id,
                "X-Task-Callback-Url": callback_url,
            }
        )
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.request(
                method, url, headers=request_headers, content=body
            )
            completed_at = datetime.now(tz=timezone.utc)
            waiting_callback = await_callback and response.status_code < 400
            record = {
                "status": "waiting_callback" if waiting_callback else (
                    "success" if response.status_code < 400 else "failed"
                ),
                "status_code": response.status_code,
                "ok": response.status_code < 400,
                "response_text": response.text,
                "elapsed_ms": response.elapsed.total_seconds() * 1000,
                "error": None,
                "completed_at": None if waiting_callback else completed_at,
            }
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.warning("job call failed url={} err={}", url, exc)
            record = {
                "status": "failed",
                "status_code": None,
                "ok": False,
                "response_text": None,
                "elapsed_ms": None,
                "error": str(exc),
                "completed_at": datetime.now(tz=timezone.utc),
            }
    await _update_run_record(run_id, record, statuses=["running"])


class JobCreate(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    cron: str
    url: AnyHttpUrl
    method: str = "GET"
    headers: dict[str, str] | None = None
    body: str | None = None
    remark: str | None = None
    await_callback: bool = False


class JobPatch(BaseModel):
    cron: str | None = None
    url: AnyHttpUrl | None = None
    method: str | None = None
    headers: dict[str, str] | None = None
    body: str | None = None
    remark: str | None = None
    await_callback: bool | None = None


class JobInfo(BaseModel):
    id: str
    cron: str
    url: AnyHttpUrl
    method: str
    headers: dict[str, str] | None
    body: str | None
    remark: str | None
    next_run_time: datetime | None
    status: str
    await_callback: bool = False


class JobResult(BaseModel):
    id: str
    status: str


class JobRun(BaseModel):
    job_id: str
    url: AnyHttpUrl
    cron: str | None
    method: str
    status_code: int | None
    ok: bool | None
    response_text: str | None
    elapsed_ms: float | None
    error: str | None
    run_at: datetime
    run_id: str = ""
    status: str = "success"
    completed_at: datetime | None = None
    callback_message: str | None = None
    callback_result: Any = None


class JobRunList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[JobRun]


class RunComplete(BaseModel):
    status: str
    message: str | None = None
    result: Any = None


class JobList(BaseModel):
    total: int
    items: list[JobInfo]


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
            "_remark": payload.remark,
            "_await_callback": payload.await_callback,
        },
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    return JobResult(id=payload.id, status="scheduled")


def _job_to_info(job) -> JobInfo:
    status = "paused" if job.next_run_time is None else "scheduled"
    return JobInfo(
        id=job.id,
        cron=job.kwargs.get("_cron"),
        url=job.kwargs.get("url"),
        method=job.kwargs.get("method", "GET"),
        headers=job.kwargs.get("headers"),
        body=job.kwargs.get("body"),
        remark=job.kwargs.get("_remark"),
        next_run_time=job.next_run_time,
        status=status,
        await_callback=job.kwargs.get("_await_callback", False),
    )


@app.get("/jobs/{job_id}", response_model=JobInfo)
async def get_job(job_id: str) -> JobInfo:
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_to_info(job)


@app.get("/jobs", response_model=JobList)
async def list_jobs() -> JobList:
    jobs = scheduler.get_jobs()
    items = [_job_to_info(job) for job in jobs]
    return JobList(total=len(items), items=items)


@app.delete("/jobs/{job_id}", response_model=JobResult)
async def delete_job(job_id: str) -> JobResult:
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    scheduler.remove_job(job_id)
    return JobResult(id=job_id, status="deleted")


@app.patch("/jobs/{job_id}", response_model=JobInfo)
async def patch_job(job_id: str, payload: JobPatch) -> JobInfo:
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    new_kwargs = dict(job.kwargs)
    update_trigger = False

    if payload.url is not None:
        new_kwargs["url"] = str(payload.url)
    if payload.method is not None:
        method = payload.method.upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise HTTPException(
                status_code=400, detail="method must be GET/POST/PUT/PATCH/DELETE"
            )
        new_kwargs["method"] = method
    if payload.headers is not None:
        new_kwargs["headers"] = payload.headers
    if payload.body is not None:
        new_kwargs["body"] = payload.body
    if payload.remark is not None:
        new_kwargs["_remark"] = payload.remark
    if payload.await_callback is not None:
        new_kwargs["_await_callback"] = payload.await_callback
    if payload.cron is not None:
        update_trigger = True
        new_cron = payload.cron
        new_kwargs["_cron"] = new_cron

    if update_trigger:
        try:
            cron_parts = new_cron.split()
            if len(cron_parts) == 5:
                trigger = CronTrigger.from_crontab(new_cron, timezone=SCHEDULER_TZINFO)
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
        scheduler.modify_job(job_id, kwargs=new_kwargs)
        scheduler.reschedule_job(job_id, trigger=trigger)
    else:
        scheduler.modify_job(job_id, kwargs=new_kwargs)

    return _job_to_info(scheduler.get_job(job_id))


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


@app.post("/runs/{run_id}/complete")
async def complete_run(run_id: str, payload: RunComplete) -> dict:
    if payload.status not in {"success", "failed"}:
        raise HTTPException(
            status_code=400, detail="status must be success or failed"
        )

    current = await asyncio.to_thread(
        runs_collection.find_one, {"run_id": run_id}, {"_id": 0}
    )
    if not current:
        raise HTTPException(status_code=404, detail="run not found")
    if current.get("status") in {"success", "failed"}:
        return {"run_id": run_id, "status": current["status"]}

    completed_at = datetime.now(tz=timezone.utc)
    await _update_run_record(
        run_id,
        {
            "status": payload.status,
            "ok": payload.status == "success",
            "completed_at": completed_at,
            "callback_message": payload.message,
            "callback_result": payload.result,
            "error": payload.message if payload.status == "failed" else None,
        },
        statuses=["running", "waiting_callback"],
    )
    return {"run_id": run_id, "status": payload.status}


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
