import numpy as np
import pytest

from audio_core.constants import SAMPLE_RATE
from audio_core.models import Grid
from audio_core.sections import (
    MIN_SEGMENT_BARS,
    SectionsError,
    kmeans,
    merge_short_runs,
    segment_song,
)

BPM = 120.0
BEATS_PER_BAR = 4
BAR_SECONDS = BEATS_PER_BAR * 60.0 / BPM

# (part, bars): the ground truth structure of the synthetic song.
STRUCTURE = [
    ("intro", 4),
    ("A", 8),
    ("B", 8),
    ("A", 8),
    ("B", 8),
    ("C", 8),
    ("B", 8),
    ("outro", 4),
]
TRUE_BOUNDARY_BARS = [0, 4, 12, 20, 28, 36, 44, 52]
N_BARS = sum(bars for _, bars in STRUCTURE)

# Chord progressions as lists of frequencies, one chord per bar.
_C, _D, _E, _F, _G, _A, _B = 261.63, 293.66, 329.63, 349.23, 392.0, 440.0, 493.88
PROGRESSIONS = {
    "intro": [[_A / 2, _C, _E]] * 4,
    "A": [[_C, _E, _G], [_G / 2, _B / 2, _D], [_A / 2, _C, _E], [_F / 2, _A / 2, _C]],
    "B": [[_F, _A, _C * 2], [_G, _B, _D * 2], [_E, _G, _B], [_A, _C * 2, _E * 2]],
    "C": [[_D * 2, _F * 2, _A * 2], [_B, _D * 2, _F * 2], [_G * 1.5, _B * 1.5, _D * 3]] * 2,
    "outro": [[_A / 2, _C, _E]] * 4,
}
# (harmonics, amplitude, hat noise amplitude) per part.
TIMBRES = {
    "intro": (2, 0.04, 0.0),
    "A": (3, 0.12, 0.0),
    "B": (8, 0.30, 0.05),
    "C": (5, 0.18, 0.0),
    "outro": (2, 0.04, 0.0),
}
VOCAL_PARTS = {"A", "B"}


def _bar(part: str, bar_in_part: int, rng: np.random.Generator) -> np.ndarray:
    harmonics, amplitude, hat = TIMBRES[part]
    chord = PROGRESSIONS[part][bar_in_part % len(PROGRESSIONS[part])]
    n = int(BAR_SECONDS * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    beat_phase = t % (BAR_SECONDS / BEATS_PER_BAR)
    envelope = np.exp(-beat_phase / 0.25)
    out = np.zeros(n)
    for freq in chord:
        for h in range(1, harmonics + 1):
            out += np.sin(2 * np.pi * freq * h * t) / h
    out *= amplitude * envelope / len(chord)
    if hat:
        eighth_phase = t % (BAR_SECONDS / 8)
        out += hat * rng.standard_normal(n) * np.exp(-eighth_phase / 0.01)
    return out


def _vocal_bar(present: bool) -> np.ndarray:
    n = int(BAR_SECONDS * SAMPLE_RATE)
    if not present:
        return np.zeros(n)
    t = np.arange(n) / SAMPLE_RATE
    return 0.2 * np.sin(2 * np.pi * 440 * t + 3 * np.sin(2 * np.pi * 5 * t))


def make_song() -> tuple[np.ndarray, np.ndarray, Grid]:
    """Mono float32 song, vocal stem and the exact grid for ``STRUCTURE``."""
    rng = np.random.default_rng(0)
    bars, vocal_bars = [], []
    for part, count in STRUCTURE:
        for i in range(count):
            bars.append(_bar(part, i, rng))
            vocal_bars.append(_vocal_bar(part in VOCAL_PARTS))
    audio = np.concatenate(bars).astype(np.float32)
    vocals = np.concatenate(vocal_bars).astype(np.float32)
    beat_interval = 60.0 / BPM
    beats = np.arange(N_BARS * BEATS_PER_BAR) * beat_interval
    grid = Grid(
        bpm=BPM,
        beats=beats.tolist(),
        downbeats=beats[::BEATS_PER_BAR].tolist(),
        time_signature="4/4",
    )
    return audio, vocals, grid


@pytest.fixture(scope="module")
def song() -> tuple[np.ndarray, np.ndarray, Grid]:
    return make_song()


@pytest.fixture(scope="module")
def segments(song):
    audio, _, grid = song
    return segment_song(audio, grid)


def _nearest_bar_error(segments, true_bar: int) -> int:
    return min(abs(seg.start_bar - true_bar) for seg in segments)


def test_boundaries_within_one_bar_of_truth(segments) -> None:
    errors = {bar: _nearest_bar_error(segments, bar) for bar in TRUE_BOUNDARY_BARS[1:]}
    assert all(error <= 1 for error in errors.values()), errors


def test_boundaries_are_downbeats_and_segments_are_long_enough(song, segments) -> None:
    _, _, grid = song
    downbeats = set(grid.downbeats)
    assert all(seg.start in downbeats for seg in segments)
    assert segments[0].start_bar == 0
    assert segments[-1].end_bar == N_BARS
    assert all(seg.n_bars >= MIN_SEGMENT_BARS for seg in segments)
    for prev, nxt in zip(segments[:-1], segments[1:], strict=True):
        assert prev.end_bar == nxt.start_bar


def test_repeated_parts_share_a_cluster(segments) -> None:
    def cluster_at(bar: int) -> int:
        return next(s.cluster for s in segments if s.start_bar <= bar < s.end_bar)

    chorus_bars = [14, 30, 46]
    verse_bars = [6, 22]
    assert len({cluster_at(b) for b in chorus_bars}) == 1
    assert len({cluster_at(b) for b in verse_bars}) == 1
    assert cluster_at(chorus_bars[0]) != cluster_at(verse_bars[0])
    assert cluster_at(38) not in {cluster_at(14), cluster_at(6)}


def test_segmentation_is_deterministic(song, segments) -> None:
    audio, _, grid = song
    assert segment_song(audio, grid) == segments


@pytest.fixture(scope="module")
def segments_with_vocals(song):
    audio, vocals, grid = song
    return segment_song(audio, grid, vocals=vocals)


def test_vocal_presence_is_measured_per_segment(segments, segments_with_vocals) -> None:
    segs = segments_with_vocals
    assert [(s.start_bar, s.cluster) for s in segs] == [(s.start_bar, s.cluster) for s in segments]
    assert all(s.vocal is not None for s in segs)
    for seg in segs:
        middle = (seg.start_bar + seg.end_bar) // 2
        if middle in range(4, 36) or middle in range(44, 52):
            assert seg.vocal > 0.5
        if middle in range(36, 44) or middle in range(52, 56):
            assert seg.vocal < 0.5


def test_energy_is_relative_to_the_song_mean(segments) -> None:
    assert segments[0].energy < 0.5 < 1.0 < max(s.energy for s in segments)


def test_short_song_is_one_segment(song) -> None:
    audio, _, grid = song
    n = int(6 * BAR_SECONDS * SAMPLE_RATE)
    short_grid = Grid(
        bpm=BPM,
        beats=[b for b in grid.beats if b < 6 * BAR_SECONDS],
        downbeats=[d for d in grid.downbeats if d < 6 * BAR_SECONDS],
        time_signature="4/4",
    )
    segs = segment_song(audio[:n], short_grid)
    assert len(segs) == 1
    assert (segs[0].start_bar, segs[0].end_bar) == (0, 6)
    # Stereo input is averaged to mono, so identical channels give the same result.
    assert segment_song(np.stack([audio[:n], audio[:n]]), short_grid) == segs


def test_grid_without_downbeats_is_an_error(song) -> None:
    audio, _, grid = song
    with pytest.raises(SectionsError, match="no downbeats"):
        segment_song(audio, grid.model_copy(update={"downbeats": []}))


def test_merge_short_runs_joins_the_more_similar_neighbor() -> None:
    # Bars 0-3 are cluster 0, bars 4-5 look like cluster 1, bars 6-13 are cluster 1.
    x = np.zeros((2, 14))
    x[0, :4] = 1.0
    x[1, 4:] = 1.0
    runs = [[0, 4, 0], [4, 6, 2], [6, 14, 1]]
    assert merge_short_runs(runs, x) == [[0, 4, 0], [4, 14, 1]]


def test_kmeans_separates_distinct_points_deterministically() -> None:
    points = np.array([[0.0, 0.0], [0.1, 0.0], [5.0, 5.0], [5.1, 5.0], [0.0, 9.0]])
    labels = kmeans(points, 3)
    assert labels[0] == labels[1] and labels[2] == labels[3]
    assert len(set(labels.tolist())) == 3
    assert np.array_equal(labels, kmeans(points, 3))
