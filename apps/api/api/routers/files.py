from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api import tokens
from api.deps import Ctx, DbSession, find_active_song
from api.services import DOWNLOAD_SUFFIXES, downloadable
from api.storage import StorageError

router = APIRouter(tags=["files"])


@router.get("/files/{token}")
def download(token: str, ctx: Ctx, session: DbSession) -> FileResponse:
    try:
        claims = tokens.verify(ctx.settings.signing_secret, token, ctx.now())
    except tokens.TokenExpired:
        raise HTTPException(410, "download link expired") from None
    except tokens.TokenInvalid:
        raise HTTPException(403, "invalid download link") from None
    try:
        find_active_song(session, ctx, claims.song_id)
    except HTTPException:
        raise HTTPException(410, "song expired") from None
    if not downloadable(claims.name):
        raise HTTPException(403, "invalid download link")
    try:
        path = ctx.storage.path(claims.song_id, claims.name)
    except StorageError:
        raise HTTPException(403, "invalid download link") from None
    if not path.is_file():
        raise HTTPException(404, "file not found")
    media_type = next(m for s, m in DOWNLOAD_SUFFIXES.items() if claims.name.endswith(s))
    return FileResponse(path, media_type=media_type, filename=path.name)
