import os
from zoneinfo import ZoneInfo
from loguru import logger


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


logger.info(
    {
        "msg": "Configuration loaded",
        "MONGO_URI": MONGO_URI,
        "MONGO_DB": MONGO_DB,
        "JOBSTORE_COLLECTION": JOBSTORE_COLLECTION,
        "RUNS_COLLECTION": RUNS_COLLECTION,
        "SCHEDULER_TZ": SCHEDULER_TZ,
        "REQUEST_TIMEOUT": REQUEST_TIMEOUT,
    }
)
