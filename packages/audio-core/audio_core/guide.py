"""Guide track: spoken counting and section cues placed sample-exactly on the timeline.

Cues come from a sample library, a directory ``assets/cues/<lang>/`` holding ``manifest.json`` and
the WAV files it lists. The guide is its own mono buffer: nothing here touches the band mix.

Counting on the count-in beats (``Timeline.count_in_beats``, bar-major):

- 4/4: ``count_1``..``count_4`` on the four beats of every count-in bar.
- 3/4 (and 2/4): ``count_1``..``count_N`` on the N beats.
- Compound meters with six or more beats per bar (6/8, 9/8, 12/8): the detected beats are eighth
  notes, so the voice counts the dotted-quarter pulse, one number every third beat. 6/8 says
  ``count_1`` on beat 1 and ``count_2`` on beat 4 (the library only has 1..4).
- Any other meter with more than four beats: ``count_1``..``count_4`` on the first four beats.

Section cues start exactly at ``timeline.section_cues(...).cue``, one bar before their section.

Overlap policy: when a cue is still sounding at the next cue onset it is truncated there (with a
3 ms fade-out), so cues never sum and never need a limiter. If two cues share an onset sample the
count wins and the section cue is dropped with a warning (this happens when the first section sits
on the first downbeat: its cue lands on count beat 1). Cues are cut at ``total_samples``, never
wrapped. A missing manifest entry or sample file is skipped and listed in ``GuideReport.warnings``.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import soxr
from pydantic import BaseModel, ValidationError

from audio_core.constants import DTYPE, SAMPLE_RATE
from audio_core.models import SectionName, Sections
from audio_core.timeline import Timeline, section_cues

COUNT_IDS = ("count_1", "count_2", "count_3", "count_4")
CUE_IDS = (*(name.value for name in SectionName), *COUNT_IDS)

# Leading samples with absolute amplitude below this (-40 dBFS) are trimmed so the first sample of
# a cue is the speech onset, not the silence recorded before it.
ONSET_THRESHOLD = 0.01
# Fade-out applied when a cue is cut by the next cue's onset.
FADE_SECONDS = 0.003

# assets/ lives at the repository root: <root>/packages/audio-core/audio_core/guide.py
DEFAULT_CUES_ROOT = Path(__file__).resolve().parents[3] / "assets" / "cues"


class CueLibraryError(RuntimeError):
    """Raised when the cue library manifest is missing or invalid."""


class CueEntry(BaseModel):
    file: str
    license: str
    source: str


class CueManifest(BaseModel):
    language: str
    voice: dict[str, Any] = {}
    cues: dict[str, CueEntry]


@dataclass(frozen=True)
class PlacedCue:
    cue_id: str
    # Onset sample in the guide buffer.
    sample: int
    # Samples actually written (after truncation at the next cue or the end of the buffer).
    length: int


@dataclass
class GuideReport:
    placed: list[PlacedCue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def default_library_dir(language: str, root: Path = DEFAULT_CUES_ROOT) -> Path:
    return root / language


def trim_leading_silence(audio: np.ndarray, threshold: float = ONSET_THRESHOLD) -> np.ndarray:
    """Drop leading samples whose absolute value is below ``threshold``."""
    loud = np.flatnonzero(np.abs(audio) >= threshold)
    return audio[loud[0] :] if loud.size else audio[:0]


def load_cue_audio(path: Path, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Load a WAV as float32 mono at ``sample_rate`` with leading silence trimmed."""
    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if rate != sample_rate:
        mono = soxr.resample(mono, rate, sample_rate)
    return trim_leading_silence(np.ascontiguousarray(mono, dtype=DTYPE))


class CueLibrary:
    """A cue sample directory; samples load lazily and a failure is reported once per cue."""

    def __init__(self, directory: Path, sample_rate: int = SAMPLE_RATE) -> None:
        self.directory = Path(directory)
        self.sample_rate = sample_rate
        manifest_path = self.directory / "manifest.json"
        try:
            self.manifest = CueManifest.model_validate_json(manifest_path.read_text("utf-8"))
        except (OSError, ValueError, ValidationError) as exc:
            raise CueLibraryError(f"cannot load cue manifest {manifest_path}: {exc}") from exc
        self._cache: dict[str, np.ndarray | str] = {}

    def get(self, cue_id: str) -> tuple[np.ndarray | None, str | None]:
        """Return ``(audio, None)``, or ``(None, reason)`` when the cue is unusable."""
        if cue_id not in self._cache:
            self._cache[cue_id] = self._load(cue_id)
        cached = self._cache[cue_id]
        return (None, cached) if isinstance(cached, str) else (cached, None)

    def _load(self, cue_id: str) -> np.ndarray | str:
        entry = self.manifest.cues.get(cue_id)
        if entry is None:
            return f"cue {cue_id!r} has no manifest entry"
        path = self.directory / entry.file
        try:
            audio = load_cue_audio(path, self.sample_rate)
        except (OSError, RuntimeError) as exc:
            return f"cue {cue_id!r} sample {entry.file!r} cannot be read: {exc}"
        if audio.size == 0:
            return f"cue {cue_id!r} sample {entry.file!r} is silent"
        return audio


def count_cue_ids(beats_per_bar: int) -> list[str | None]:
    """Cue id spoken on each beat of a count-in bar (None = silent beat); see module docstring."""
    if beats_per_bar >= 6 and beats_per_bar % 3 == 0:
        pulses = min(beats_per_bar // 3, len(COUNT_IDS))
        return [
            COUNT_IDS[b // 3] if b % 3 == 0 and b // 3 < pulses else None
            for b in range(beats_per_bar)
        ]
    return [COUNT_IDS[b] if b < len(COUNT_IDS) else None for b in range(beats_per_bar)]


def _count_events(timeline: Timeline) -> list[tuple[int, int, str]]:
    pattern = count_cue_ids(timeline.beats_per_bar)
    events = []
    for i, sample in enumerate(timeline.count_in_beats):
        cue_id = pattern[i % timeline.beats_per_bar]
        if cue_id is not None:
            events.append((sample, 1, cue_id))
    return events


def render_guide(
    timeline: Timeline,
    total_samples: int,
    sections: Sections | None,
    library: CueLibrary,
) -> tuple[np.ndarray, GuideReport]:
    """Render the guide as a mono float32 buffer of exactly ``total_samples`` samples."""
    if library.sample_rate != timeline.sample_rate:
        raise CueLibraryError(
            f"cue library rate {library.sample_rate} Hz does not match "
            f"timeline rate {timeline.sample_rate} Hz"
        )
    report = GuideReport()
    # (sample, kind, cue_id); kind 0 = section cue, 1 = count, so the count sorts last on a tie.
    events = _count_events(timeline)
    if sections is not None:
        for placed in section_cues(timeline, sections.sections):
            cue_id = placed.section.name.value
            if placed.cue is None:
                report.warnings.append(f"cue {cue_id!r} would start before sample 0; skipped")
            else:
                events.append((placed.cue, 0, cue_id))
    events.sort(key=lambda e: (e[0], e[1]))

    kept: list[tuple[int, str]] = []
    for i, (sample, _kind, cue_id) in enumerate(events):
        if i + 1 < len(events) and events[i + 1][0] == sample:
            report.warnings.append(
                f"cue {cue_id!r} shares onset sample {sample} with a higher-priority cue; dropped"
            )
        elif sample >= total_samples:
            report.warnings.append(f"cue {cue_id!r} starts after the end of the track; skipped")
        else:
            kept.append((sample, cue_id))

    guide = np.zeros(total_samples, dtype=DTYPE)
    fade = int(FADE_SECONDS * timeline.sample_rate)
    warned: set[str] = set()
    for i, (sample, cue_id) in enumerate(kept):
        audio, reason = library.get(cue_id)
        if audio is None:
            if cue_id not in warned:
                warned.add(cue_id)
                report.warnings.append(f"{reason}; skipped")
            continue
        next_onset = kept[i + 1][0] if i + 1 < len(kept) else total_samples
        limit = min(len(audio), next_onset - sample, total_samples - sample)
        piece = audio[:limit].copy()
        if limit < len(audio) and limit == next_onset - sample:
            ramp = min(fade, limit)
            piece[limit - ramp :] *= np.linspace(1.0, 0.0, ramp, endpoint=False, dtype=DTYPE)
        guide[sample : sample + limit] = piece
        report.placed.append(PlacedCue(cue_id, sample, limit))
    # Resampling can overshoot a full-scale sample slightly; cues never overlap, so no limiter.
    np.clip(guide, -1.0, 1.0, out=guide)
    return guide, report
