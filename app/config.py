import os
from urllib.parse import urlsplit, urlunsplit
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


def _redact_uri(uri: str) -> str:
    parts = urlsplit(uri)
    if not parts.password:
        return uri
    username = parts.username or ""
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    redacted_netloc = f"{username}:***@{host}{port}"
    return urlunsplit((parts.scheme, redacted_netloc, parts.path, parts.query, parts.fragment))


logger.info(
    {
        "msg": "Configuration loaded",
        "MONGO_URI": _redact_uri(MONGO_URI),
        "MONGO_DB": MONGO_DB,
        "JOBSTORE_COLLECTION": JOBSTORE_COLLECTION,
        "RUNS_COLLECTION": RUNS_COLLECTION,
        "SCHEDULER_TZ": SCHEDULER_TZ,
        "REQUEST_TIMEOUT": REQUEST_TIMEOUT,
    }
)
