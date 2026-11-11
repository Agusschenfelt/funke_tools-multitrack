"""FastAPI application factory.

``app`` loads its settings from the environment when the server starts (fail fast if
``SIGNING_SECRET`` is missing); tests call ``create_app`` with explicit settings and doubles.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.bodylimit import BodyLimitMiddleware
from api.cleanup import cleanup_loop
from api.config import Settings, cors_origins_from_env
from api.db import make_engine, make_session_factory
from api.deps import AppContext
from api.queueing import JobQueue, RqQueue
from api.ratelimit import RateLimiter, RedisRateLimiter
from api.routers import files, jobs, songs
from api.storage import LocalStorage


def utc_now() -> datetime:
    return datetime.now(UTC)


def build_context(
    settings: Settings,
    queue: JobQueue | None,
    clock: Callable[[], datetime] | None,
    limiter: RateLimiter | None,
) -> AppContext:
    engine = make_engine(settings.database_url)
    return AppContext(
        settings=settings,
        session_factory=make_session_factory(engine),
        storage=LocalStorage(settings.storage_root),
        queue=queue or RqQueue(settings.redis_url, settings.result_ttl_seconds),
        clock=clock or utc_now,
        limiter=limiter or RedisRateLimiter(settings.redis_url),
    )


def create_app(
    settings: Settings | None = None,
    *,
    queue: JobQueue | None = None,
    clock: Callable[[], datetime] | None = None,
    limiter: RateLimiter | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings is None:
            app.state.ctx = build_context(Settings.from_env(), queue, clock, limiter)
        ctx = app.state.ctx
        interval = ctx.settings.cleanup_interval_seconds
        task = asyncio.create_task(cleanup_loop(ctx, interval)) if interval > 0 else None
        app.state.cleanup_task = task
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="Multitrack API", version="0.1.0", lifespan=lifespan)
    if settings is not None:
        app.state.ctx = build_context(settings, queue, clock, limiter)
    app.add_middleware(BodyLimitMiddleware)
    origins = settings.cors_origins if settings is not None else cors_origins_from_env()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origins),
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["Content-Disposition"],
        )
    app.include_router(songs.router)
    app.include_router(jobs.router)
    app.include_router(files.router)
    return app


app = create_app()
