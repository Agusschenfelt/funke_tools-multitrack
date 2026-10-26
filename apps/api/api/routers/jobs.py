from fastapi import APIRouter, HTTPException

from api.deps import Ctx, DbSession, find_active_song
from api.models import Job
from api.queueing import FINISHED
from api.schemas import JobOut
from api.services import make_link, pack_stored_name, sync_job

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, ctx: Ctx, session: DbSession) -> JobOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    song = find_active_song(session, ctx, job.song_id)
    sync_job(session, ctx, job)
    download_url = None
    if job.kind == "stagepack" and job.status == FINISHED and job.result:
        filename = job.result.get("filename")
        stored = pack_stored_name(ctx, job, filename) if filename else None
        if stored:
            download_url = make_link(ctx, song, stored).url
    return JobOut(
        job_id=job.id,
        song_id=job.song_id,
        kind=job.kind,
        status=job.status,
        stage=job.stage,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        result=job.result,
        download_url=download_url,
    )
