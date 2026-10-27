"""Pydantic data models for pipeline outputs."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from audio_core.constants import SAMPLE_RATE


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
    # Time of the first detected beat when the grid was extended backwards over a beatless
    # intro; beats and downbeats before it are estimated. None for grids as detected.
    extrapolated_until: float | None = None


class KeyInfo(BaseModel):
    key: str
    mode: str
    camelot: str
    compatible: list[str]
    note: str | None = None


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
    shifts: int = 1
    elapsed_seconds: float
    load_seconds: float
    audio_seconds: float
    samples: int
    sample_rate: int = SAMPLE_RATE
    stems: list[Stem]


class SectionName(StrEnum):
    """Fixed section vocabulary; pack files translate it per language and destination."""

    INTRO = "intro"
    VERSE = "verse"
    VERSE_2 = "verse_2"
    PRE_CHORUS = "pre_chorus"
    CHORUS = "chorus"
    BRIDGE = "bridge"
    SOLO = "solo"
    INSTRUMENTAL = "instrumental"
    BREAK = "break"
    OUTRO = "outro"
    TAG = "tag"


class Section(BaseModel):
    name: SectionName
    # Seconds in the original song, before the count-in pad is applied.
    start: float = Field(ge=0, allow_inf_nan=False)
    label: str | None = None
    # Set by automatic detection; hand-written files omit both.
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    cluster: int | None = Field(default=None, ge=0)


class Sections(BaseModel):
    """Optional ``sections.json`` input: section starts in original-song time."""

    source: str | None = None
    sections: list[Section]

    @model_validator(mode="after")
    def _sorted_and_unique(self) -> "Sections":
        starts = [section.start for section in self.sections]
        if len(set(starts)) != len(starts):
            raise ValueError("section starts must be unique")
        if starts != sorted(starts):
            raise ValueError("sections must be sorted by start time")
        return self


class StagePackOptions(BaseModel):
    # "prime" joins the destinations once its naming convention is verified.
    destination: Literal["playback", "daw"]
    count_in_bars: Literal[1, 2] = 1
    click_sound: Literal["classic", "cowbell", "woodblock", "rimshot"] = "classic"
    subdivision: Literal["quarter", "eighth"] = "quarter"
    straight_grid: bool = False
    sample_rate: Literal[44100, 48000] = 44100
    include_vocals: bool = False
    # Keep the estimated grid over a beatless intro; False starts click and cues at the first beat.
    extend_grid: bool = True
    language: Literal["es", "en"] = "es"
