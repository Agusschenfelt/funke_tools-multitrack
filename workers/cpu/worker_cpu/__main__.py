"""Start an RQ worker on the ``cpu`` queue (env: REDIS_URL, STORAGE_ROOT)."""

from redis import Redis
from rq import Queue, Worker

from worker_cpu.config import QUEUE_NAME, redis_url
from worker_cpu.security import JSON_SERIALIZER, AllowlistJob


def build_worker(connection: Redis, worker_class: type[Worker] | None = None) -> Worker:
    """A worker on the ``cpu`` queue that reads JSON job records and runs allowlisted jobs only."""
    queue = Queue(
        QUEUE_NAME, connection=connection, job_class=AllowlistJob, serializer=JSON_SERIALIZER
    )
    return (worker_class or Worker)(
        [queue], connection=connection, job_class=AllowlistJob, serializer=JSON_SERIALIZER
    )


def main() -> None:
    build_worker(Redis.from_url(redis_url())).work()


if __name__ == "__main__":
    main()
