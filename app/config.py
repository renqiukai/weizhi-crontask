import os
from zoneinfo import ZoneInfo


def _get_env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value else default


MONGO_URI = _get_env("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB = _get_env("MONGO_DB", "weizhi_crontask")
JOBSTORE_COLLECTION = _get_env("JOBSTORE_COLLECTION", "apscheduler_jobs")
RUNS_COLLECTION = _get_env("RUNS_COLLECTION", "job_runs")
SCHEDULER_TZ = _get_env("SCHEDULER_TZ", "Asia/Shanghai")
SCHEDULER_TZINFO = ZoneInfo(SCHEDULER_TZ)
REQUEST_TIMEOUT = float(_get_env("REQUEST_TIMEOUT", "10"))
