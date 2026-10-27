"""Shared logic: download links, artifact listing, job creation and job state sync."""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
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
from api.schemas import ArtifactLink, Artifacts, PreviewMeta

DOWNLOAD_PREFIXES = (names.PACKS_PREFIX, names.STEMS_PREFIX)
DOWNLOAD_SUFFIXES = {".zip": "application/zip", ".wav": "audio/wav", ".m4a": "audio/mp4"}


def downloadable(name: str) -> bool:
    """Only packs, stem audio and stem previews can be served through tokens.

    Compressed ``.m4a`` is served only as a stem preview (``stems/preview/<stem>.m4a``).
    """
    if not name.startswith(DOWNLOAD_PREFIXES):
        return False
    if name.endswith(".m4a"):
        return name.startswith(names.PREVIEW_PREFIX)
    return any(name.endswith(s) for s in DOWNLOAD_SUFFIXES)


def token_expiry(ctx: AppContext, song: Song) -> datetime:
    """now + TTL, never beyond 24 h and never past the song's own expiry."""
    return min(ctx.now() + timedelta(seconds=ctx.settings.token_ttl_seconds), song.expires_at)


def make_link(ctx: AppContext, song: Song, name: str) -> ArtifactLink:
    expires_at = token_expiry(ctx, song)
    token = tokens.sign(ctx.settings.signing_secret, song.id, name, expires_at)
    return ArtifactLink(
        name=name.rsplit("/", 1)[1], url=f"/files/{token}", token_expires_at=expires_at
    )


def pack_stored_name(ctx: AppContext, job: Job, filename: str) -> str | None:
    """Stored object of a finished stagepack job, or None when it is not in storage.

    Only this job's own ``packs/<job_id>/<filename>`` counts. A flat ``packs/<filename>`` (the
    pre-per-job layout) is deliberately not a fallback: it cannot be tied to a job, so it could be
    another job's pack of the same name.
    """
    name = names.pack_object_name(job.id, filename)
    try:
        return name if ctx.storage.exists(job.song_id, name) else None
    except names.StorageError:
        return None


def _preview_meta(ctx: AppContext, song: Song) -> PreviewMeta | None:
    """Preview encoding facts from ``stemset.json``; None when absent or unreadable."""
    try:
        data = json.loads(ctx.storage.get_bytes(song.id, names.STEMSET))
        info = data["preview"]
        return PreviewMeta(
            samples=int(data["samples"]),
            sample_rate=int(data.get("sample_rate", 44100)),
            priming_samples=int(info["priming_samples"]),
        )
    except (names.StorageError, KeyError, TypeError, ValueError):
        return None


def artifacts_of(session: Session, ctx: AppContext, song: Song) -> Artifacts:
    store = ctx.storage
    state = session.get(SectionsState, song.id)
    stems = [
        n
        for n in store.list_names(song.id, names.STEMS_PREFIX)
        if downloadable(n) and "/" not in n[len(names.STEMS_PREFIX) :]
    ]
    previews = [n for n in store.list_names(song.id, names.PREVIEW_PREFIX) if downloadable(n)]
    packs = [n for n in store.list_names(song.id, names.PACKS_PREFIX) if downloadable(n)]
    return Artifacts(
        analysis=store.exists(song.id, names.ANALYSIS),
        sections=store.exists(song.id, names.SECTIONS),
        sections_edited=bool(state and state.edited),
        stems=[make_link(ctx, song, n) for n in stems],
        previews=[make_link(ctx, song, n) for n in previews],
        preview=_preview_meta(ctx, song) if previews else None,
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
    the error surfaced (ambiguous outcome), so the job row is kept and marked failed with an
    explicit error rather than deleted: a worker that still runs it can then never produce an
    untracked job, and the client simply retries to get a fresh job id. The pack row of a failed
    stagepack job is removed, since nothing can ever fill it in.
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
        # The pack row only exists to receive the filename of its job; that job is now terminal
        # and failed, so the row would stay empty forever. Drop it with the failure recorded.
        session.query(Pack).filter(Pack.job_id == job_id).delete()
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


class Outcome(Enum):
    """What storage says about a job the queue forgot."""

    FINISHED = "finished"  # the worker left its result marker for this very job
    LOST = "lost"  # no marker: the job never completed, or was never run


@dataclass(frozen=True)
class ArtifactOutcome:
    outcome: Outcome
    result: Any = None  # the job's raw return value, only for FINISHED


def _artifact_outcome(ctx: AppContext, job: Job) -> ArtifactOutcome:
    """Read the result marker ``jobs/<job_id>.json`` the worker wrote for this exact job.

    Terminal outcomes must not depend on RQ remembering the job. The worker writes the marker
    after its artifacts and before the job returns, so a marker proves this job succeeded; it is
    keyed by job id, so neither an older run's output nor another pack of the song can be mistaken
    for it. A missing or unreadable marker means the job did not complete. Raises
    ``StorageError`` when storage itself cannot answer.
    """
    name = names.job_result_name(job.id)
    if not ctx.storage.exists(job.song_id, name):
        return ArtifactOutcome(Outcome.LOST)
    try:
        return ArtifactOutcome(
            Outcome.FINISHED, json.loads(ctx.storage.get_bytes(job.song_id, name))["result"]
        )
    except (ValueError, KeyError, TypeError):
        return ArtifactOutcome(Outcome.LOST)  # a marker that does not parse proves nothing


def _fail_if_lost(session: Session, ctx: AppContext, job: Job, now: datetime) -> Job:
    """Settle a non-terminal row the queue forgot, once the grace period has passed.

    The grace covers the short window between committing the row and the enqueue landing. A
    missing RQ entry whose result marker is in storage means the job finished and RQ's record
    expired before anyone polled: it is recorded as finished. Without a marker it is lost.
    """
    if now - job.created_at < timedelta(seconds=ctx.settings.lost_job_grace_seconds):
        return job
    try:
        found = _artifact_outcome(ctx, job)
    except names.StorageError:
        return job  # storage hiccup says nothing about the job; decide on a later poll
    job.finished_at = now
    if found.outcome is Outcome.LOST:
        job.status = FAILED
        job.error = LOST_JOB_ERROR
    else:
        job.status = FINISHED
        job.result = _normalize_result(job.kind, found.result)
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
