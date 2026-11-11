"""Expiry cleanup: delete songs past their 24 h life together with their files.

``cleanup_expired`` removes each expired ``Song`` row with its Jobs, Packs and SectionsState
(deleted explicitly, so it does not depend on the database enforcing ``ON DELETE CASCADE``; SQLite
does not by default) and its storage directory. Storage goes first and the rows last, so a crash
in between leaves rows that the next sweep retries instead of orphaned data nobody tracks.

It runs in two ways:

* inside the API process, every ``CLEANUP_INTERVAL_SECONDS`` (default 900, ``0`` disables) from
  the FastAPI lifespan (``cleanup_loop``);
* once, from cron or a one-off container: ``python -m api.cleanup``.

One song failing to delete (a storage error) is logged and skipped; the sweep continues and the
song, still expired, is retried by the next sweep. Songs with a queued or running job are left
alone until they are ``INFLIGHT_MARGIN`` past expiry, so a slow job is not deleted from under its
worker, but a job stuck forever cannot keep a song alive indefinitely.

Safe to run from several places at once: deleting an already-deleted song (its storage or its rows
vanishing mid-sweep) counts as success, not as a failure.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import delete, select

from api.deps import AppContext
from api.models import Job, Pack, SectionsState, Song
from api.queueing import ACTIVE

log = logging.getLogger(__name__)

INFLIGHT_MARGIN = timedelta(hours=1)


@dataclass
class SweepReport:
    deleted: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped_in_flight: list[str] = field(default_factory=list)


def sweep_expired(ctx: AppContext) -> SweepReport:
    """Delete every expired song, isolating failures per song; return what happened."""
    now = ctx.now()
    report = SweepReport()
    with ctx.session_factory() as session:
        # Plain tuples, not ORM instances: another sweep (or a commit of ours) deleting or
        # expiring a row must not make the loop touch a stale object.
        expired = [
            (song_id, expires_at)
            for song_id, expires_at in session.execute(
                select(Song.id, Song.expires_at).where(Song.expires_at <= now)
            )
        ]
        for song_id, expires_at in expired:
            try:
                active = session.scalar(
                    select(Job.id).where(Job.song_id == song_id, Job.status.in_(ACTIVE)).limit(1)
                )
                if active is not None and now < expires_at + INFLIGHT_MARGIN:
                    report.skipped_in_flight.append(song_id)
                    continue
                ctx.storage.delete_song(song_id)
                session.execute(delete(Job).where(Job.song_id == song_id))
                session.execute(delete(Pack).where(Pack.song_id == song_id))
                session.execute(delete(SectionsState).where(SectionsState.song_id == song_id))
                # A row already removed by a concurrent sweep deletes zero rows: still success.
                session.execute(delete(Song).where(Song.id == song_id))
                session.commit()
                report.deleted.append(song_id)
            except Exception:  # noqa: BLE001 - one poisoned song must not abort the sweep
                session.rollback()
                if _already_gone(session, ctx, song_id):
                    report.deleted.append(song_id)
                    continue
                log.exception("expiry cleanup failed for song %s; will retry next sweep", song_id)
                report.failed.append(song_id)
    return report


def _already_gone(session, ctx: AppContext, song_id: str) -> bool:
    """True when a concurrent sweep removed both the row and the files while we were failing."""
    try:
        return session.get(Song, song_id) is None and not ctx.storage.list_names(song_id)
    except Exception:  # noqa: BLE001 - cannot tell; let the caller count it as failed
        session.rollback()
        return False


def cleanup_expired(ctx: AppContext) -> list[str]:
    """Delete every song with ``expires_at <= now``; return the deleted song ids."""
    return sweep_expired(ctx).deleted


async def cleanup_loop(
    ctx: AppContext,
    interval: float,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Sweep immediately, then every ``interval`` seconds, until cancelled. Errors are logged."""
    while True:
        try:
            report = await asyncio.to_thread(sweep_expired, ctx)
            if report.deleted or report.failed or report.skipped_in_flight:
                log.info(
                    "expiry cleanup: deleted %d, failed %d, deferred %d (job in flight)",
                    len(report.deleted),
                    len(report.failed),
                    len(report.skipped_in_flight),
                )
        except Exception:  # noqa: BLE001 - one failed sweep must not stop the schedule
            log.exception("expiry cleanup failed")
        await sleep(interval)


def main() -> None:
    from api.config import Settings
    from api.main import build_context

    ctx = build_context(Settings.from_env(), None, None, None)
    report = sweep_expired(ctx)
    print(f"deleted {len(report.deleted)} expired song(s)")
    for song_id in report.deleted:
        print(song_id)
    if report.failed:
        print(f"failed {len(report.failed)} song(s); retried next sweep")
    if report.skipped_in_flight:
        print(f"deferred {len(report.skipped_in_flight)} song(s) with a job in flight")


if __name__ == "__main__":
    main()
