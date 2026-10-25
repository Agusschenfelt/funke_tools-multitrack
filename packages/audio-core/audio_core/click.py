"""Click track: numpy-synthesized sounds placed on the beat grid, sample-exact.

Positions come from the count-in ``Timeline`` (integer samples at the internal rate). A click
starts at its onset sample with no pre-delay, so the onset equals the beat sample. Resampling for
export is not done here.
"""

from bisect import bisect_left
from dataclasses import dataclass
from typing import Literal

import numpy as np

from audio_core.constants import DTYPE, SAMPLE_RATE
from audio_core.models import StagePackOptions
from audio_core.timeline import Timeline

ClickSound = Literal["classic", "cowbell", "woodblock", "rimshot"]

# Peak levels (linear): -3 dBFS accent, -7 dBFS normal, -12 dBFS subdivision.
ACCENT_PEAK = 0.708
NORMAL_PEAK = 0.447
SUBDIVISION_PEAK = 0.25

# A beat within this many seconds of a downbeat is that downbeat: the grid rounds beats and
# downbeats independently, so the same instant can differ by a sample or two.
_DOWNBEAT_TOLERANCE_SECONDS = 0.001

# A gap wider than this many beat intervals breaks a subdivision chain (long intro before the
# count-in): the click before the gap is treated like the last beat.
_GAP_FACTOR = 1.5


@dataclass(frozen=True)
class ClickEvent:
    sample: int
    accent: bool
    subdivision: bool = False


def _envelope(n: int, decay_ms: float, sample_rate: int) -> np.ndarray:
    t = np.arange(n) / sample_rate
    return np.exp(-t / (decay_ms / 1000.0))


def _tone(freq: float, n: int, sample_rate: int) -> np.ndarray:
    # Cosine phase: the first sample is the maximum, so the onset is sharp and exactly at sample 0.
    return np.cos(2 * np.pi * freq * np.arange(n) / sample_rate)


def _shape(name: str, accent: bool, sample_rate: int) -> np.ndarray:
    """Unnormalized click waveform; accent is higher pitched."""
    n = int(0.06 * sample_rate)
    pitch = 1.33 if accent else 1.0
    if name == "classic":
        wave = _tone(1500 * pitch, n, sample_rate) * _envelope(n, 8, sample_rate)
    elif name == "cowbell":
        wave = (
            np.sign(_tone(560 * pitch, n, sample_rate))
            + np.sign(_tone(845 * pitch, n, sample_rate))
        ) * _envelope(n, 14, sample_rate)
    elif name == "woodblock":
        wave = (
            _tone(1100 * pitch, n, sample_rate) + 0.4 * _tone(2640 * pitch, n, sample_rate)
        ) * _envelope(n, 6, sample_rate)
    elif name == "rimshot":
        noise = np.random.default_rng(7).uniform(-1.0, 1.0, n)
        wave = (0.7 * noise * _envelope(n, 3, sample_rate)) + (
            _tone(1700 * pitch, n, sample_rate) * _envelope(n, 10, sample_rate)
        )
    else:
        raise ValueError(f"unknown click sound {name!r}")
    return wave


def click_sample(
    name: str, *, accent: bool, subdivision: bool = False, sample_rate: int = SAMPLE_RATE
) -> np.ndarray:
    """One click, peak-normalized: accent loudest, subdivision softest."""
    wave = _shape(name, accent, sample_rate)
    peak = ACCENT_PEAK if accent else SUBDIVISION_PEAK if subdivision else NORMAL_PEAK
    return (wave / np.max(np.abs(wave)) * peak).astype(DTYPE)


def _is_downbeat(sample: int, downbeats: tuple[int, ...], tolerance: int) -> bool:
    """True when ``sample`` is within ``tolerance`` samples of a (sorted) downbeat."""
    i = bisect_left(downbeats, sample)
    near = downbeats[max(i - 1, 0) : i + 1]
    return any(abs(d - sample) <= tolerance for d in near)


def _main_beats(timeline: Timeline, total_samples: int, straight_grid: bool) -> list[ClickEvent]:
    bpb = timeline.beats_per_bar
    events = [
        ClickEvent(sample, accent=k % bpb == 0) for k, sample in enumerate(timeline.count_in_beats)
    ]
    tolerance = round(_DOWNBEAT_TOLERANCE_SECONDS * timeline.sample_rate)
    first = timeline.first_downbeat
    start = timeline.count_in_start
    if straight_grid:
        # Evenly spaced at the mean tempo from the first downbeat on; bar position by counting.
        interval = timeline.bar_samples / bpb
        i = 0
        while (sample := first + round(i * interval)) < total_samples:
            events.append(ClickEvent(sample, accent=i % bpb == 0))
            i += 1
    else:
        # Detected beats inside the count-in window are replaced by the count-in clicks.
        events.extend(
            ClickEvent(sample, accent=_is_downbeat(sample, timeline.downbeats, tolerance))
            for sample in timeline.beats
            if sample < start or sample >= first
        )
    events = [e for e in events if e.sample < total_samples]
    return sorted(events, key=lambda e: e.sample)


def _subdivisions(beats: list[ClickEvent], beat_samples: float) -> list[ClickEvent]:
    """A soft click halfway to the next beat; the last beat (or one before a gap) reuses the
    interval that led to it."""
    out = []
    previous_gap = round(beat_samples)
    for i, beat in enumerate(beats):
        gap = beats[i + 1].sample - beat.sample if i + 1 < len(beats) else None
        if gap is not None and gap <= _GAP_FACTOR * beat_samples:
            half = gap // 2
            previous_gap = gap
        else:
            half = previous_gap // 2
        out.append(ClickEvent(beat.sample + half, accent=False, subdivision=True))
    return out


def click_events(
    timeline: Timeline, total_samples: int, options: StagePackOptions
) -> list[ClickEvent]:
    """Every click onset in sample order: count-in, grid beats and optional eighth subdivisions."""
    beats = _main_beats(timeline, total_samples, options.straight_grid)
    if options.subdivision != "eighth":
        return beats
    beat_samples = timeline.bar_samples / timeline.beats_per_bar
    subs = [e for e in _subdivisions(beats, beat_samples) if e.sample < total_samples]
    return sorted(beats + subs, key=lambda e: e.sample)


def render_click(timeline: Timeline, total_samples: int, options: StagePackOptions) -> np.ndarray:
    """Mono float32 click track of exactly ``total_samples``; late clicks are truncated."""
    audio = np.zeros(total_samples, dtype=DTYPE)
    cache: dict[tuple[bool, bool], np.ndarray] = {}
    for event in click_events(timeline, total_samples, options):
        key = (event.accent, event.subdivision)
        if key not in cache:
            cache[key] = click_sample(
                options.click_sound,
                accent=event.accent,
                subdivision=event.subdivision,
                sample_rate=timeline.sample_rate,
            )
        sound = cache[key][: total_samples - event.sample]
        audio[event.sample : event.sample + len(sound)] += sound
    return np.clip(audio, -1.0, 1.0)
