"""Start an RQ worker on the ``cpu`` queue (env: REDIS_URL, STORAGE_ROOT)."""

from redis import Redis
from rq import Queue, Worker

from worker_cpu.config import QUEUE_NAME, redis_url


def main() -> None:
    connection = Redis.from_url(redis_url())
    queue = Queue(QUEUE_NAME, connection=connection)
    Worker([queue], connection=connection).work()


if __name__ == "__main__":
    main()
