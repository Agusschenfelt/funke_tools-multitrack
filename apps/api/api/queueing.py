"""Job queue boundary.

The API enqueues by dotted path string (``"worker_cpu.jobs.analyze_job"``) so it never imports
worker code. ``JobQueue`` is the seam tests replace with an in-memory double.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from rq.serializers import JSONSerializer

QUEUE_NAME = "cpu"
# Job records are JSON on both sides (never pickle): see ``worker_cpu.security``.
SERIALIZER = JSONSerializer

ANALYZE_FUNC = "worker_cpu.jobs.analyze_job"
SEPARATE_FUNC = "worker_cpu.jobs.separate_job"
STAGEPACK_FUNC = "worker_cpu.jobs.stagepack_job"


class JobState(StrEnum):
    """The public job statuses; the single source for the DB column, the API schema and checks."""

    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"


QUEUED, RUNNING, FINISHED, FAILED = (
    JobState.QUEUED,
    JobState.RUNNING,
    JobState.FINISHED,
    JobState.FAILED,
)
TERMINAL = frozenset({FINISHED, FAILED})
ACTIVE = (QUEUED, RUNNING)
# The RQ statuses that map onto them.
_RQ_STATUS = {
    "queued": QUEUED,
    "deferred": QUEUED,
    "scheduled": QUEUED,
    "started": RUNNING,
    "finished": FINISHED,
    "failed": FAILED,
    "stopped": FAILED,
    "canceled": FAILED,
}


def map_status(rq_status: str | None) -> JobState:
    """Map an RQ status to queued | running | finished | failed (unknown counts as queued)."""
    return _RQ_STATUS.get(rq_status or "", QUEUED)


class QueueUnavailable(RuntimeError):
    """The queue backend (Redis) cannot be reached."""


@dataclass
class RemoteJob:
    """What the API needs to know about an RQ job."""

    status: str  # raw RQ status
    stage: str | None = None
    error: str | None = None
    result: Any = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class JobQueue(Protocol):
    def enqueue(
        self, func: str, args: tuple, kwargs: dict, *, job_id: str, timeout: int
    ) -> None: ...

    def fetch(self, job_id: str) -> RemoteJob | None:
        """The RQ job, or None when the queue does not know it (expired or removed).

        Raises ``QueueUnavailable`` when the backend cannot be reached, so callers never mistake
        an outage for a lost job.
        """
        ...


def aware_utc(value: datetime | None) -> datetime | None:
    """RQ stores naive UTC datetimes; return them as timezone-aware UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _last_line(text: str | None) -> str | None:
    if not text:
        return None
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return lines[-1][:500] if lines else None


class RqQueue:
    """RQ-backed queue on the ``cpu`` queue. Redis is contacted lazily."""

    def __init__(self, redis_url: str, result_ttl: int, name: str = QUEUE_NAME) -> None:
        """``result_ttl``: seconds RQ keeps job records (``Settings.result_ttl_seconds``)."""
        self.redis_url = redis_url
        self.result_ttl = result_ttl
        self.name = name
        self._connection = None

    def _conn(self):
        from redis import Redis

        if self._connection is None:
            self._connection = Redis.from_url(self.redis_url)
        return self._connection

    def enqueue(self, func: str, args: tuple, kwargs: dict, *, job_id: str, timeout: int) -> None:
        from redis.exceptions import RedisError
        from rq import Queue

        try:
            Queue(self.name, connection=self._conn(), serializer=SERIALIZER).enqueue(
                func,
                args=args,
                kwargs=kwargs,
                job_id=job_id,
                job_timeout=timeout,
                result_ttl=self.result_ttl,
                failure_ttl=self.result_ttl,
            )
        except RedisError as exc:
            raise QueueUnavailable(str(exc)) from exc

    def fetch(self, job_id: str) -> RemoteJob | None:
        from redis.exceptions import RedisError
        from rq.exceptions import NoSuchJobError
        from rq.job import Job

        try:
            job = Job.fetch(job_id, connection=self._conn(), serializer=SERIALIZER)
            status = job.get_status(refresh=True)
            return RemoteJob(
                # RQ returns a JobStatus enum whose str() is "JobStatus.FINISHED"; use its value.
                status=str(getattr(status, "value", status)),
                stage=job.meta.get("stage"),
                error=_last_line(job.latest_result().exc_string if job.latest_result() else None)
                if job.is_failed
                else None,
                result=job.result if job.is_finished else None,
                started_at=aware_utc(job.started_at),
                ended_at=aware_utc(job.ended_at),
            )
        except NoSuchJobError:
            return None
        except RedisError as exc:
            raise QueueUnavailable(str(exc)) from exc
