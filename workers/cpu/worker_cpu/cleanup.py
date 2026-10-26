"""Orphan sweep: a storage-only safety net behind the API's expiry cleanup.

The API owns song lifetime: its sweep deletes expired songs together with their database rows,
and it holds a song back while a job is queued or running. This module never competes with that
sweep. It only removes song directories that are *orphans*: older than the song TTL plus
``ORPHAN_GRACE_HOURS`` (6 h), which means the API had every chance to delete them and did not
(database reset, a row that is gone, repeated failures). Directories with a live job lock
(``jobs/<job_id>.lock``, written by running jobs) are skipped; a lock older than
``LOCK_STALE_HOURS`` belongs to a crashed worker and no longer protects anything.

Nothing schedules it: it is not part of the compose stack. Run it by hand or from cron when
needed (``docker compose -f infra/docker-compose.yml run --rm worker-cpu python -m
worker_cpu.cleanup``). ``cleanup_job`` is a plain function so tests can inject the clock.

One song failing to delete is logged and skipped; the others are still processed and the failed
one is retried on the next run. Rows left behind for a directory it removed are cleaned by the
API sweep.

The TTL comes from ``SONG_TTL_HOURS`` (default 24), the same setting the API reads.
"""

import logging
import os
import time

from worker_cpu.config import get_storage
from worker_cpu.storage import Storage

log = logging.getLogger(__name__)

DEFAULT_SONG_TTL_HOURS = 24
ORPHAN_GRACE_HOURS = 6
LOCK_STALE_HOURS = 6


def song_ttl_seconds() -> float:
    """Single source for the song lifetime: ``SONG_TTL_HOURS`` env var, default 24."""
    raw = os.environ.get("SONG_TTL_HOURS")
    try:
        hours = float(raw) if raw else DEFAULT_SONG_TTL_HOURS
    except ValueError:
        log.warning("invalid SONG_TTL_HOURS=%r; using %s", raw, DEFAULT_SONG_TTL_HOURS)
        hours = DEFAULT_SONG_TTL_HOURS
    if hours <= 0:
        log.warning("non-positive SONG_TTL_HOURS=%r; using %s", raw, DEFAULT_SONG_TTL_HOURS)
        hours = DEFAULT_SONG_TTL_HOURS
    return hours * 3600


def cleanup_job(
    now: float | None = None,
    *,
    max_age_seconds: float | None = None,
    storage: Storage | None = None,
) -> list[str]:
    """Delete orphaned songs; return the deleted ids.

    A song is an orphan when its oldest artifact is older than ``max_age_seconds`` (default: song
    TTL + ``ORPHAN_GRACE_HOURS``; ``now`` is POSIX seconds) and no fresh job lock protects it.
    """
    store = storage or get_storage()
    current = time.time() if now is None else now
    limit = (
        song_ttl_seconds() + ORPHAN_GRACE_HOURS * 3600
        if max_age_seconds is None
        else max_age_seconds
    )
    deleted = []
    for entry in store.list_songs():
        if current - entry.created > limit:
            if (
                entry.lock_modified is not None
                and current - entry.lock_modified < LOCK_STALE_HOURS * 3600
            ):
                log.info("song %s has a live job lock; leaving it", entry.song_id)
                continue
            try:
                store.delete_song(entry.song_id)
            except Exception:  # noqa: BLE001 - one poisoned song must not abort the sweep
                log.exception("could not delete song %s; will retry next run", entry.song_id)
                continue
            deleted.append(entry.song_id)
    return deleted


def main() -> None:
    deleted = cleanup_job()
    print(f"deleted {len(deleted)} orphaned song(s)")
    for song_id in deleted:
        print(song_id)


if __name__ == "__main__":
    main()
