"""Count-in timeline: sample-exact positions for the Stage Pack.

Everything here is pure and works in integer samples at the internal rate. Seconds only enter
through ``round(seconds * sample_rate)``, so every position the pack uses is derived once.

Rule: bar length is ``beats_per_bar`` times the mean beat interval of the first two detected bars.
The count-in (1 or 2 bars) ends exactly on the first detected downbeat ``t0``. If the song starts
too close to ``t0`` to fit the count-in, ``pad_samples`` of silence are prepended to every stem and
all grid and section positions shift by the pad.

Meter: ``beats_per_bar`` is the numerator of ``Grid.time_signature``. ``analysis`` infers the
signature from the number of detected beats per bar (6 beats per bar becomes "6/8"), so in 6/8 the
beats are the six eighth notes, and the click and count-in follow those six beats.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from audio_core.constants import SAMPLE_RATE
from audio_core.models import Grid, Section


class TimelineError(ValueError):
    """Raised when the grid cannot support a count-in timeline."""


@dataclass(frozen=True)
class Timeline:
    sample_rate: int
    beats_per_bar: int
    count_in_bars: int
    bar_samples: int
    pad_samples: int
    # Sample positions after the pad shift (index 0 of every stem is sample zero).
    count_in_beats: tuple[int, ...]
    beats: tuple[int, ...]
    downbeats: tuple[int, ...]

    @property
    def count_in_samples(self) -> int:
        return self.count_in_bars * self.bar_samples

    @property
    def first_downbeat(self) -> int:
        return self.downbeats[0]

    @property
    def count_in_start(self) -> int:
        """Sample where the count-in begins; 0 unless a long intro precedes ``t0``."""
        return self.first_downbeat - self.count_in_samples

    def total_samples(self, original_samples: int) -> int:
        """Length of every pack WAV for a song of ``original_samples`` samples."""
        return original_samples + self.pad_samples


@dataclass(frozen=True)
class SectionCue:
    section: Section
    # Section start snapped to the nearest downbeat, in shifted samples.
    downbeat: int
    # One bar earlier, or None when that would fall before sample 0.
    cue: int | None


def beats_per_bar(time_signature: str) -> int:
    try:
        count = int(time_signature.split("/")[0])
    except ValueError as exc:
        raise TimelineError(f"unsupported time signature {time_signature!r}") from exc
    if count < 1:
        raise TimelineError(f"unsupported time signature {time_signature!r}")
    return count


def mean_beat_interval(grid: Grid, bpb: int) -> float:
    """Mean beat interval in seconds over the first two bars starting at the first downbeat.

    Falls back to every detected beat when fewer than two bars of beats follow ``t0``. Beats must
    be finite and strictly increasing; duplicates or unsorted beats would yield a zero or negative
    interval and a meaningless bar length, so they are rejected.
    """
    beats = grid.beats
    if len(beats) < 2:
        raise TimelineError("at least two beats are required to build a timeline")
    if not all(math.isfinite(b) for b in beats):
        raise TimelineError("beats must be finite numbers")
    if any(later <= earlier for earlier, later in zip(beats, beats[1:], strict=False)):
        raise TimelineError(
            "beats must be strictly increasing (found a duplicate or unsorted beat)"
        )
    first = next((i for i, b in enumerate(beats) if b >= grid.downbeats[0] - 1e-3), len(beats))
    window = beats[first : first + 2 * bpb + 1]
    if len(window) < 2 * bpb + 1:
        window = beats
    interval = (window[-1] - window[0]) / (len(window) - 1)
    if not math.isfinite(interval) or interval <= 0:
        raise TimelineError(f"beat interval must be positive, got {interval!r}")
    return interval


def build_timeline(grid: Grid, count_in_bars: int = 1, sample_rate: int = SAMPLE_RATE) -> Timeline:
    """Build the count-in timeline for ``grid`` at ``sample_rate`` (the internal rate)."""
    if count_in_bars not in (1, 2):
        raise TimelineError(f"count_in_bars must be 1 or 2, got {count_in_bars!r}")
    if not grid.downbeats:
        raise TimelineError("at least one downbeat is required to place the count-in")
    if not all(math.isfinite(d) for d in grid.downbeats) or any(
        later <= earlier for earlier, later in zip(grid.downbeats, grid.downbeats[1:], strict=False)
    ):
        raise TimelineError("downbeats must be finite and strictly increasing")
    bpb = beats_per_bar(grid.time_signature)
    interval = mean_beat_interval(grid, bpb)
    bar_samples = round(bpb * interval * sample_rate)
    if bar_samples < 1:
        raise TimelineError("bar length rounds to zero samples")
    count_in_samples = count_in_bars * bar_samples
    pad = max(0, count_in_samples - round(grid.downbeats[0] * sample_rate))

    first_downbeat = round(grid.downbeats[0] * sample_rate) + pad
    count_in_start = first_downbeat - count_in_samples
    total_beats = count_in_bars * bpb
    count_in_beats = tuple(
        count_in_start + round(k * count_in_samples / total_beats) for k in range(total_beats)
    )
    return Timeline(
        sample_rate=sample_rate,
        beats_per_bar=bpb,
        count_in_bars=count_in_bars,
        bar_samples=bar_samples,
        pad_samples=pad,
        count_in_beats=count_in_beats,
        beats=tuple(round(b * sample_rate) + pad for b in grid.beats),
        downbeats=tuple(round(d * sample_rate) + pad for d in grid.downbeats),
    )


def snap_to_downbeat(timeline: Timeline, seconds: float) -> int:
    """Index of the downbeat nearest to an original-song time (ties go to the earlier one).

    A time before the first downbeat snaps to the first one and a time after the last snaps to the
    last. Negative or non-finite times are rejected.
    """
    if not math.isfinite(seconds) or seconds < 0:
        raise TimelineError(f"section time must be finite and not negative, got {seconds!r}")
    target = round(seconds * timeline.sample_rate) + timeline.pad_samples
    return min(range(len(timeline.downbeats)), key=lambda i: abs(timeline.downbeats[i] - target))


def cue_position(downbeats: Sequence[int], index: int, bar_samples: int) -> int | None:
    """Cue sample for the section on ``downbeats[index]``: the bar preceding it.

    "One bar" means the span to the previous detected downbeat, so with uneven bars the cue sits on
    that downbeat and the distance to the section is not necessarily ``bar_samples``. For the first
    downbeat there is no previous one, so it falls back to the section downbeat minus
    ``bar_samples``. A cue that would land before sample 0 is skipped (None) rather than clamped,
    because a clamped cue would not start exactly one bar ahead of its section.
    """
    cue = downbeats[index - 1] if index > 0 else downbeats[index] - bar_samples
    return cue if cue >= 0 else None


def section_cues(timeline: Timeline, sections: Sequence[Section]) -> list[SectionCue]:
    """Snap each section to a downbeat and place its cue one bar earlier."""
    cues = []
    for section in sections:
        index = snap_to_downbeat(timeline, section.start)
        cues.append(
            SectionCue(
                section=section,
                downbeat=timeline.downbeats[index],
                cue=cue_position(timeline.downbeats, index, timeline.bar_samples),
            )
        )
    return cues
