"""Pydantic data models for pipeline outputs."""

from pydantic import BaseModel


class ModelVersion(BaseModel):
    name: str
    version: str
    source: str | None = None


class Grid(BaseModel):
    bpm: float
    beats: list[float]
    downbeats: list[float]
    time_signature: str
    notes: list[str] = []


class KeyInfo(BaseModel):
    key: str
    mode: str
    camelot: str
    compatible: list[str]


class Loudness(BaseModel):
    integrated_lufs: float
    true_peak_dbtp: float


class Analysis(BaseModel):
    source: str
    duration: float
    sample_rate: int
    grid: Grid | None
    key: KeyInfo | None
    loudness: Loudness | None
    models: dict[str, ModelVersion]


class Stem(BaseModel):
    name: str
    path: str
    samples: int


class StemSet(BaseModel):
    source: str
    model: ModelVersion
    device: str
    elapsed_seconds: float
    samples: int
    stems: list[Stem]
