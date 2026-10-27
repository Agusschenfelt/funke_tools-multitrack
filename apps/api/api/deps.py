"""Application context and request dependencies."""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from api.config import Settings
from api.models import Song
from api.queueing import JobQueue
from api.storage import LocalStorage


@dataclass
class AppContext:
    settings: Settings
    session_factory: sessionmaker[Session]
    storage: LocalStorage
    queue: JobQueue
    clock: Callable[[], datetime]

    def now(self) -> datetime:
        return self.clock()


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


Ctx = Annotated[AppContext, Depends(get_ctx)]


def get_session(ctx: Ctx) -> Iterator[Session]:
    with ctx.session_factory() as session:
        yield session


DbSession = Annotated[Session, Depends(get_session)]


def find_active_song(session: Session, ctx: AppContext, song_id: str) -> Song:
    """The song when it exists and has not expired; 404 otherwise (also for malformed ids)."""
    try:
        normalized = str(uuid.UUID(song_id))
    except ValueError:
        raise HTTPException(404, "song not found") from None
    song = session.get(Song, normalized)
    if song is None or song.expires_at <= ctx.now():
        raise HTTPException(404, "song not found")
    return song


def get_song(song_id: str, ctx: Ctx, session: DbSession) -> Song:
    return find_active_song(session, ctx, song_id)


ActiveSong = Annotated[Song, Depends(get_song)]
