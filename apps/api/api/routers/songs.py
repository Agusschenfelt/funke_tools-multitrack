import hashlib
import json
import tempfile
from datetime import timedelta
from pathlib import Path, PurePosixPath

from audio_core.models import Sections, StagePackOptions
from fastapi import APIRouter, HTTPException, Response, UploadFile
from pydantic import ValidationError

from api import queueing
from api import storage as names
from api.deps import ActiveSong, Ctx, DbSession
from api.models import SectionsState, Song
from api.schemas import (
    AnalyzeRequest,
    JobCreated,
    SectionsOut,
    SeparateRequest,
    SongDetail,
    UploadOut,
)
from api.services import artifacts_of, create_job, require_source

router = APIRouter(tags=["songs"])

CHUNK = 1024 * 1024
ANALYZE_TIMEOUT = 30 * 60
SEPARATE_TIMEOUT = 60 * 60
STAGEPACK_TIMEOUT = 30 * 60


def _clean_filename(raw: str | None) -> str:
    name = PurePosixPath((raw or "").replace("\\", "/")).name.strip()
    if not name or name in (".", ".."):
        raise HTTPException(400, "missing file name")
    return name[:255]


@router.post("/songs", response_model=UploadOut, status_code=201)
def upload_song(file: UploadFile, response: Response, ctx: Ctx, session: DbSession) -> UploadOut:
    """Store an upload, hashing while streaming; reuse a live song with the same audio hash."""
    filename = _clean_filename(file.filename)
    extension = Path(filename).suffix.lower()
    if extension not in ctx.settings.allowed_extensions:
        raise HTTPException(
            415, f"unsupported file type; allowed: {sorted(ctx.settings.allowed_extensions)}"
        )
    digest = hashlib.sha256()
    size = 0
    limit = ctx.settings.max_upload_bytes
    with tempfile.NamedTemporaryFile(dir=ctx.storage.incoming_dir(), delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            while chunk := file.file.read(CHUNK):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(
                        413, f"file exceeds the {ctx.settings.max_upload_mb} MB limit"
                    )
                digest.update(chunk)
                tmp.write(chunk)
        except BaseException:
            tmp.close()
            tmp_path.unlink(missing_ok=True)
            raise
    try:
        if size == 0:
            raise HTTPException(400, "empty file")
        sha256 = digest.hexdigest()
        now = ctx.now()
        existing = (
            session.query(Song)
            .filter(Song.sha256 == sha256, Song.expires_at > now)
            .order_by(Song.created_at.desc())
            .first()
        )
        if existing is not None:
            response.status_code = 200
            return UploadOut(**_song_fields(existing), reused=True)
        song = Song(
            filename=filename,
            sha256=sha256,
            created_at=now,
            expires_at=now + timedelta(hours=ctx.settings.song_ttl_hours),
        )
        session.add(song)
        session.flush()
        ctx.storage.put_file(song.id, f"{names.SOURCE_PREFIX}{extension}", tmp_path)
        session.commit()
        return UploadOut(**_song_fields(song), reused=False)
    finally:
        tmp_path.unlink(missing_ok=True)


def _song_fields(song: Song) -> dict:
    return {
        "id": song.id,
        "filename": song.filename,
        "sha256": song.sha256,
        "duration": song.duration,
        "created_at": song.created_at,
        "expires_at": song.expires_at,
    }


@router.get("/songs/{song_id}", response_model=SongDetail)
def get_song_detail(song: ActiveSong, ctx: Ctx, session: DbSession) -> SongDetail:
    return SongDetail(**_song_fields(song), artifacts=artifacts_of(session, ctx, song))


@router.post("/songs/{song_id}/analyze", response_model=JobCreated, status_code=202)
def analyze(
    song: ActiveSong, ctx: Ctx, session: DbSession, body: AnalyzeRequest | None = None
) -> JobCreated:
    require_source(ctx, song)
    request = body or AnalyzeRequest()
    job_id = create_job(
        session,
        ctx,
        song,
        "analyze",
        queueing.ANALYZE_FUNC,
        (song.id,),
        {"sections": request.sections, "source_name": song.filename},
        timeout=ANALYZE_TIMEOUT,
    )
    return JobCreated(job_id=job_id)


@router.post("/songs/{song_id}/separate", response_model=JobCreated, status_code=202)
def separate(
    song: ActiveSong, ctx: Ctx, session: DbSession, body: SeparateRequest | None = None
) -> JobCreated:
    require_source(ctx, song)
    request = body or SeparateRequest()
    job_id = create_job(
        session,
        ctx,
        song,
        "separate",
        queueing.SEPARATE_FUNC,
        (song.id,),
        {"model": request.model, "source_name": song.filename},
        timeout=SEPARATE_TIMEOUT,
    )
    return JobCreated(job_id=job_id)


@router.post("/songs/{song_id}/stagepack", response_model=JobCreated, status_code=202)
def stagepack(song: ActiveSong, options: StagePackOptions, ctx: Ctx, session: DbSession):
    missing = [
        label
        for label, name in (("analysis", names.ANALYSIS), ("stems", names.STEMSET))
        if not ctx.storage.exists(song.id, name)
    ]
    if missing:
        raise HTTPException(409, f"missing artifacts: {', '.join(missing)}; run them first")
    # The pack title comes from the analysis `source`, which analyze_job labels with the upload
    # filename; stagepack_job takes no source_name.
    payload = options.model_dump()
    job_id = create_job(
        session,
        ctx,
        song,
        "stagepack",
        queueing.STAGEPACK_FUNC,
        (song.id, payload),
        {},
        timeout=STAGEPACK_TIMEOUT,
        pack_options=payload,
    )
    return JobCreated(job_id=job_id)


@router.get("/songs/{song_id}/analysis")
def get_analysis(song: ActiveSong, ctx: Ctx) -> Response:
    try:
        data = ctx.storage.get_bytes(song.id, names.ANALYSIS)
    except names.StorageError:
        raise HTTPException(404, "analysis not available") from None
    return Response(data, media_type="application/json")


def _sections_out(session: DbSession, song: Song, sections: Sections) -> SectionsOut:
    state = session.get(SectionsState, song.id)
    return SectionsOut(
        source=sections.source,
        sections=sections.sections,
        edited=bool(state and state.edited),
        updated_at=state.updated_at if state else None,
    )


@router.get("/songs/{song_id}/sections", response_model=SectionsOut)
def get_sections(song: ActiveSong, ctx: Ctx, session: DbSession) -> SectionsOut:
    try:
        raw = ctx.storage.get_bytes(song.id, names.SECTIONS)
        sections = Sections.model_validate(json.loads(raw))
    except names.StorageError:
        raise HTTPException(404, "sections not available") from None
    except (ValueError, ValidationError):
        raise HTTPException(500, "stored sections are invalid") from None
    return _sections_out(session, song, sections)


@router.put("/songs/{song_id}/sections", response_model=SectionsOut)
def put_sections(song: ActiveSong, body: Sections, ctx: Ctx, session: DbSession) -> SectionsOut:
    """Validated by the audio-core model (sorted, unique starts, known names); marks edited."""
    ctx.storage.put_bytes(song.id, names.SECTIONS, body.model_dump_json(indent=2).encode())
    state = session.get(SectionsState, song.id)
    if state is None:
        state = SectionsState(song_id=song.id, edited=True, updated_at=ctx.now())
        session.add(state)
    else:
        state.edited = True
        state.updated_at = ctx.now()
    session.commit()
    return _sections_out(session, song, body)
