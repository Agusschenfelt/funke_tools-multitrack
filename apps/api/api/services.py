"""Shared logic: download links, artifact listing, job creation and job state sync."""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from api import storage as names
from api import tokens
from api.deps import AppContext
from api.models import Job, Pack, SectionsState, Song
from api.queueing import (
    FAILED,
    FINISHED,
    QUEUED,
    RUNNING,
    TERMINAL,
    QueueUnavailable,
    map_status,
)
from api.schemas import ArtifactLink, Artifacts

DOWNLOAD_PREFIXES = (names.PACKS_PREFIX, names.STEMS_PREFIX)
DOWNLOAD_SUFFIXES = {".zip": "application/zip", ".wav": "audio/wav"}


def downloadable(name: str) -> bool:
    """Only packs and stem audio can be served through tokens."""
    return name.startswith(DOWNLOAD_PREFIXES) and any(name.endswith(s) for s in DOWNLOAD_SUFFIXES)


def token_expiry(ctx: AppContext, song: Song) -> datetime:
    """now + TTL, never beyond 24 h and never past the song's own expiry."""
    return min(ctx.now() + timedelta(seconds=ctx.settings.token_ttl_seconds), song.expires_at)


def make_link(ctx: AppContext, song: Song, name: str) -> ArtifactLink:
    expires_at = token_expiry(ctx, song)
    token = tokens.sign(ctx.settings.signing_secret, song.id, name, expires_at)
    return ArtifactLink(
        name=name.split("/", 1)[1], url=f"/files/{token}", token_expires_at=expires_at
    )


def artifacts_of(session: Session, ctx: AppContext, song: Song) -> Artifacts:
    store = ctx.storage
    state = session.get(SectionsState, song.id)
    stems = [n for n in store.list_names(song.id, names.STEMS_PREFIX) if downloadable(n)]
    packs = [n for n in store.list_names(song.id, names.PACKS_PREFIX) if downloadable(n)]
    return Artifacts(
        analysis=store.exists(song.id, names.ANALYSIS),
        sections=store.exists(song.id, names.SECTIONS),
        sections_edited=bool(state and state.edited),
        stems=[make_link(ctx, song, n) for n in stems],
        packs=[make_link(ctx, song, n) for n in packs],
    )


def require_source(ctx: AppContext, song: Song) -> None:
    if not any("/" not in n for n in ctx.storage.list_names(song.id, names.SOURCE_PREFIX)):
        raise HTTPException(409, "song has no stored source audio")


ENQUEUE_FAILED_ERROR = "enqueue failed: the queue was unavailable (outcome unknown); submit again"


def create_job(
    session: Session,
    ctx: AppContext,
    song: Song,
    kind: str,
    func: str,
    args: tuple,
    kwargs: dict,
    *,
    timeout: int,
    pack_options: dict | None = None,
) -> str:
    """Commit the Job row, then enqueue on RQ with the same id; 503 if the queue is down.

    The row is committed first so a fast worker (or a status poll) never sees an RQ job without
    its row. If enqueueing fails the 503 is returned, but Redis may have accepted the job before
    the error surfaced (ambiguous outcome), so the rows are kept and the job is marked failed with
    an explicit error rather than deleted: a worker that still runs it can then never produce an
    untracked job, and the client simply retries to get a fresh job id.
    """
    job_id = str(uuid.uuid4())
    now = ctx.now()
    session.add(Job(id=job_id, song_id=song.id, kind=kind, status=QUEUED, created_at=now))
    if pack_options is not None:
        session.add(
            Pack(
                song_id=song.id,
                job_id=job_id,
                destination=pack_options["destination"],
                options=pack_options,
                created_at=now,
            )
        )
    session.commit()
    try:
        ctx.queue.enqueue(func, args, kwargs, job_id=job_id, timeout=timeout)
    except QueueUnavailable:
        row = session.get(Job, job_id)
        if row is not None:
            row.status = FAILED
            row.error = ENQUEUE_FAILED_ERROR
            row.finished_at = ctx.now()
            session.commit()
        raise HTTPException(503, "job queue unavailable") from None
    return job_id


def _normalize_result(kind: str, result: Any) -> dict | None:
    if result is None:
        return None
    if isinstance(result, dict):
        return result
    # stagepack_job returns the ZIP name.
    return {"filename": str(result)} if kind == "stagepack" else {"value": result}


def sync_job(session: Session, ctx: AppContext, job: Job) -> Job:
    """Merge the live RQ state into the DB row. Terminal rows are immutable."""
    if job.status in TERMINAL:
        return job
    now = ctx.now()
    try:
        remote = ctx.queue.fetch(job.id)
    except QueueUnavailable:
        return job  # an outage says nothing about the job; keep the last known state
    if remote is None:
        return _fail_if_lost(session, ctx, job, now)
    status = map_status(remote.status)
    job.status = status
    job.stage = remote.stage or job.stage
    if status in (RUNNING, FINISHED, FAILED) and job.started_at is None:
        job.started_at = remote.started_at or now
    if status in TERMINAL:
        job.finished_at = remote.ended_at or now
    if status == FAILED:
        job.error = remote.error or "job failed"
    if status == FINISHED:
        job.result = _normalize_result(job.kind, remote.result)
        _apply_finished(session, ctx, job)
    session.commit()
    return job


LOST_JOB_ERROR = "job lost: the queue no longer knows it (expired or removed before finishing)"


def _artifact_outcome(session: Session, ctx: AppContext, job: Job) -> dict | None | bool:
    """Did the worker leave its output in storage? False when not; else the result to record.

    Terminal outcomes must not depend on RQ remembering the job. The worker writes its artifact
    before the job finishes, so the artifact proves success. Limitation: a re-run of a kind whose
    artifact already existed (analyze, separate) cannot be told apart from its earlier output.
    """
    store = ctx.storage
    if job.kind == "analyze":
        return None if store.exists(job.song_id, names.ANALYSIS) else False
    if job.kind == "separate":
        return None if store.exists(job.song_id, names.STEMSET) else False
    if job.kind == "stagepack":
        claimed = {
            p.filename
            for p in session.query(Pack).filter(Pack.song_id == job.song_id)
            if p.filename and p.job_id != job.id
        }
        for name in store.list_names(job.song_id, names.PACKS_PREFIX):
            filename = name.split("/", 1)[1]
            if name.endswith(".zip") and filename not in claimed:
                return {"filename": filename}
        return False
    return False


def _fail_if_lost(session: Session, ctx: AppContext, job: Job, now: datetime) -> Job:
    """Settle a non-terminal row the queue forgot, once the grace period has passed.

    The grace covers the short window between committing the row and the enqueue landing. A
    missing RQ entry whose artifact is in storage means the job finished and RQ's result expired
    before anyone polled: it is recorded as finished. Only absent artifacts mean it is lost.
    """
    if now - job.created_at < timedelta(seconds=ctx.settings.lost_job_grace_seconds):
        return job
    try:
        outcome = _artifact_outcome(session, ctx, job)
    except names.StorageError:
        return job  # storage hiccup says nothing about the job; decide on a later poll
    job.finished_at = now
    if outcome is False:
        job.status = FAILED
        job.error = LOST_JOB_ERROR
    else:
        job.status = FINISHED
        job.result = outcome
        _apply_finished(session, ctx, job)
    session.commit()
    return job


def _apply_finished(session: Session, ctx: AppContext, job: Job) -> None:
    if job.kind == "stagepack" and job.result and job.result.get("filename"):
        pack = session.query(Pack).filter(Pack.job_id == job.id).one_or_none()
        if pack is not None:
            pack.filename = job.result["filename"]
    if job.kind == "analyze":
        song = session.get(Song, job.song_id)
        if song is not None and song.duration is None:
            try:
                data = json.loads(ctx.storage.get_bytes(song.id, names.ANALYSIS))
                song.duration = float(data["duration"])
            except (names.StorageError, KeyError, TypeError, ValueError):
                pass
