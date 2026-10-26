"""Storage expiry: delete every song stored for longer than the song TTL (24 hours by default).

``cleanup_job`` is a plain function so it can run as an RQ job, from tests with an injected
clock, or from the command line. A song's age is the mtime of its oldest artifact (the upload),
so later pipeline outputs never extend its life; files never outlive the TTL.

Scheduling (no RQ scheduler needed): run it from cron, a compose sidecar or any timer::

    */15 * * * * python -m worker_cpu.cleanup

The API's own sweep also deletes expired songs (database rows and storage). This job works on
storage alone, by file age: it removes any song directory older than the TTL, whether or not the
API still has a row for it (for example after a database reset or a failed API sweep). Rows left
behind for a directory it removed are cleaned by the API sweep.

One song failing to delete is logged and skipped; the others are still processed and the failed
one is retried on the next run.

The TTL comes from ``SONG_TTL_HOURS`` (default 24). The API's ``song_ttl_hours`` setting is the
other half of the same policy: keep both at the same value.
"""

import logging
import os
import time

from worker_cpu.config import get_storage
from worker_cpu.storage import Storage

log = logging.getLogger(__name__)

DEFAULT_SONG_TTL_HOURS = 24


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
    """Delete songs older than ``max_age_seconds`` (POSIX ``now``); return the deleted ids."""
    store = storage or get_storage()
    current = time.time() if now is None else now
    limit = song_ttl_seconds() if max_age_seconds is None else max_age_seconds
    deleted = []
    for entry in store.list_songs():
        if current - entry.created > limit:
            try:
                store.delete_song(entry.song_id)
            except Exception:  # noqa: BLE001 - one poisoned song must not abort the sweep
                log.exception("could not delete song %s; will retry next run", entry.song_id)
                continue
            deleted.append(entry.song_id)
    return deleted


def main() -> None:
    deleted = cleanup_job()
    print(f"deleted {len(deleted)} expired song(s)")
    for song_id in deleted:
        print(song_id)


if __name__ == "__main__":
    main()
