"""Storage expiry: delete every song stored for longer than 24 hours.

``cleanup_job`` is a plain function so it can run as an RQ job, from tests with an injected
clock, or from the command line. A song's age is the mtime of its oldest artifact (the upload),
so later pipeline outputs never extend its life; files never outlive 24 h.

Scheduling (no RQ scheduler needed): run it from cron, a compose sidecar or any timer::

    */15 * * * * python -m worker_cpu.cleanup

The API removes expired songs (database rows and storage) itself; this job is the storage-side
safety net for directories that have no database row (for example after a database reset).
"""

import time

from worker_cpu.config import get_storage
from worker_cpu.storage import Storage

MAX_AGE_SECONDS = 24 * 3600


def cleanup_job(
    now: float | None = None,
    *,
    max_age_seconds: float = MAX_AGE_SECONDS,
    storage: Storage | None = None,
) -> list[str]:
    """Delete songs older than ``max_age_seconds`` (POSIX ``now``); return the deleted ids."""
    store = storage or get_storage()
    current = time.time() if now is None else now
    deleted = []
    for entry in store.list_songs():
        if current - entry.created > max_age_seconds:
            store.delete_song(entry.song_id)
            deleted.append(entry.song_id)
    return deleted


def main() -> None:
    deleted = cleanup_job()
    print(f"deleted {len(deleted)} expired song(s)")
    for song_id in deleted:
        print(song_id)


if __name__ == "__main__":
    main()
