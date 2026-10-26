"""Expiry cleanup: delete songs past their 24 h life together with their files.

``cleanup_expired`` removes each expired ``Song`` row with its Jobs, Packs and SectionsState
(deleted explicitly, so it does not depend on the database enforcing ``ON DELETE CASCADE``; SQLite
does not by default) and its storage directory. Storage goes first and the rows last, so a crash
in between leaves rows that the next sweep retries instead of orphaned data nobody tracks.

It runs in two ways:

* inside the API process, every ``CLEANUP_INTERVAL_SECONDS`` (default 900, ``0`` disables) from
  the FastAPI lifespan (``cleanup_loop``);
* once, from cron or a one-off container: ``python -m api.cleanup``.

Safe to run from several places at once: deleting an already-deleted song is a no-op.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import delete, select

from api.deps import AppContext
from api.models import Job, Pack, SectionsState, Song

log = logging.getLogger(__name__)


def cleanup_expired(ctx: AppContext) -> list[str]:
    """Delete every song with ``expires_at <= now``; return the deleted song ids."""
    now = ctx.now()
    with ctx.session_factory() as session:
        expired = list(session.scalars(select(Song.id).where(Song.expires_at <= now)))
        for song_id in expired:
            ctx.storage.delete_song(song_id)
            session.execute(delete(Job).where(Job.song_id == song_id))
            session.execute(delete(Pack).where(Pack.song_id == song_id))
            session.execute(delete(SectionsState).where(SectionsState.song_id == song_id))
            session.execute(delete(Song).where(Song.id == song_id))
            session.commit()
    return expired


async def cleanup_loop(
    ctx: AppContext,
    interval: float,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Sweep immediately, then every ``interval`` seconds, until cancelled. Errors are logged."""
    while True:
        try:
            deleted = await asyncio.to_thread(cleanup_expired, ctx)
            if deleted:
                log.info("expiry cleanup deleted %d song(s)", len(deleted))
        except Exception:  # noqa: BLE001 - one failed sweep must not stop the schedule
            log.exception("expiry cleanup failed")
        await sleep(interval)


def main() -> None:
    from api.config import Settings
    from api.main import build_context

    ctx = build_context(Settings.from_env(), None, None)
    deleted = cleanup_expired(ctx)
    print(f"deleted {len(deleted)} expired song(s)")
    for song_id in deleted:
        print(song_id)


if __name__ == "__main__":
    main()
