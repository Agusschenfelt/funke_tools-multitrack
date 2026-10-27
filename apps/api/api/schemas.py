"""Request and response schemas."""

from datetime import datetime
from typing import Any, Literal

from audio_core.models import Section
from pydantic import BaseModel, Field

from api.queueing import JobState

SEPARATION_MODELS = ("htdemucs_6s", "htdemucs_ft")


class SongOut(BaseModel):
    id: str
    filename: str
    sha256: str
    duration: float | None
    created_at: datetime
    expires_at: datetime


class UploadOut(SongOut):
    reused: bool


class ArtifactLink(BaseModel):
    name: str
    url: str
    token_expires_at: datetime


class Artifacts(BaseModel):
    analysis: bool
    sections: bool
    sections_edited: bool
    stems: list[ArtifactLink]
    packs: list[ArtifactLink]


class SongDetail(SongOut):
    artifacts: Artifacts


class AnalyzeRequest(BaseModel):
    sections: bool = True


class SeparateRequest(BaseModel):
    model: Literal["htdemucs_6s", "htdemucs_ft"] = "htdemucs_6s"


class JobCreated(BaseModel):
    job_id: str


class JobOut(BaseModel):
    job_id: str
    song_id: str
    kind: str
    status: JobState
    stage: str | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result: dict[str, Any] | None = None
    download_url: str | None = None


class SectionsOut(BaseModel):
    source: str | None
    sections: list[Section] = Field(default_factory=list)
    edited: bool
    updated_at: datetime | None
