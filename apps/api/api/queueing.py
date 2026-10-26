"""Job queue boundary.

The API enqueues by dotted path string (``"worker_cpu.jobs.analyze_job"``) so it never imports
worker code. ``JobQueue`` is the seam tests replace with an in-memory double.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

QUEUE_NAME = "cpu"
# RQ keeps finished/failed job records this long. Twice the 24 h song life, so a record outlives
# the song it belongs to even for jobs that finish late in its life; the API also falls back to
# storage artifacts when a record is gone (services._fail_if_lost).
RESULT_TTL_SECONDS = 48 * 3600

ANALYZE_FUNC = "worker_cpu.jobs.analyze_job"
SEPARATE_FUNC = "worker_cpu.jobs.separate_job"
STAGEPACK_FUNC = "worker_cpu.jobs.stagepack_job"

# Public job statuses and the RQ statuses that map onto them.
QUEUED, RUNNING, FINISHED, FAILED = "queued", "running", "finished", "failed"
TERMINAL = frozenset({FINISHED, FAILED})
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


def map_status(rq_status: str | None) -> str:
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

    def __init__(self, redis_url: str, name: str = QUEUE_NAME) -> None:
        self.redis_url = redis_url
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
            Queue(self.name, connection=self._conn()).enqueue(
                func,
                args=args,
                kwargs=kwargs,
                job_id=job_id,
                job_timeout=timeout,
                result_ttl=RESULT_TTL_SECONDS,
                failure_ttl=RESULT_TTL_SECONDS,
            )
        except RedisError as exc:
            raise QueueUnavailable(str(exc)) from exc

    def fetch(self, job_id: str) -> RemoteJob | None:
        from redis.exceptions import RedisError
        from rq.exceptions import NoSuchJobError
        from rq.job import Job

        try:
            job = Job.fetch(job_id, connection=self._conn())
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
