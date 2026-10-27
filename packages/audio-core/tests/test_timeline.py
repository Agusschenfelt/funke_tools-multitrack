import numpy as np
import pytest

from audio_core.constants import SAMPLE_RATE
from audio_core.models import Grid, Section, SectionName
from audio_core.timeline import (
    TimelineError,
    build_timeline,
    cue_position,
    section_cues,
    snap_to_downbeat,
)

SR = SAMPLE_RATE


def make_grid(bpm: float, bpb: int, t0: float, bars: int = 8, signature: str | None = None) -> Grid:
    interval = 60.0 / bpm
    beats = [t0 + i * interval for i in range(bars * bpb)]
    return Grid(
        bpm=bpm,
        beats=beats,
        downbeats=beats[::bpb],
        time_signature=signature or f"{bpb}/4",
    )


def test_four_four_pad_and_count_in_are_exact() -> None:
    # 120 BPM: beat 22050 samples, bar 88200. t0 = 0.5 s = 22050, so pad = 66150.
    timeline = build_timeline(make_grid(120, 4, 0.5), count_in_bars=1)
    assert timeline.bar_samples == 88200
    assert timeline.pad_samples == 88200 - 22050
    assert timeline.first_downbeat == 88200
    assert timeline.count_in_start == 0
    assert timeline.count_in_beats == (0, 22050, 44100, 66150)
    assert timeline.total_samples(1000) == 1000 + 66150


def test_two_bar_count_in() -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5), count_in_bars=2)
    assert timeline.pad_samples == 2 * 88200 - 22050
    assert timeline.first_downbeat == 2 * 88200
    assert timeline.count_in_beats == tuple(k * 22050 for k in range(8))


def test_three_four() -> None:
    # 90 BPM: beat 29400 samples, bar 88200 with three beats.
    timeline = build_timeline(make_grid(90, 3, 1.0), count_in_bars=1)
    assert timeline.beats_per_bar == 3
    assert timeline.bar_samples == 88200
    assert timeline.pad_samples == 88200 - 44100
    assert timeline.count_in_beats == (0, 29400, 58800)
    assert timeline.first_downbeat - timeline.count_in_beats[-1] == 29400


def test_six_eight_uses_six_beats_per_bar() -> None:
    # Six detected beats per bar (eighth notes) at 180 beats/min: beat 14700, bar 88200.
    timeline = build_timeline(make_grid(180, 6, 0.0, signature="6/8"), count_in_bars=1)
    assert timeline.beats_per_bar == 6
    assert timeline.bar_samples == 88200
    assert len(timeline.count_in_beats) == 6
    assert timeline.count_in_beats[1] - timeline.count_in_beats[0] == 14700


def test_pickup_longer_than_count_in_needs_no_pad() -> None:
    timeline = build_timeline(make_grid(120, 4, 10.0), count_in_bars=1)
    assert timeline.pad_samples == 0
    assert timeline.first_downbeat == 10 * SR
    assert timeline.count_in_start == 10 * SR - 88200
    assert timeline.count_in_start > 0
    assert timeline.count_in_beats[0] == timeline.count_in_start
    assert timeline.total_samples(5000) == 5000


def test_shifted_grid_keeps_original_spacing() -> None:
    grid = make_grid(120, 4, 0.5)
    timeline = build_timeline(grid)
    expected = np.round(np.array(grid.beats) * SR).astype(int) + timeline.pad_samples
    assert timeline.beats == tuple(expected)
    assert timeline.downbeats[0] == timeline.first_downbeat


def test_bar_length_uses_first_two_bars_only() -> None:
    grid = make_grid(120, 4, 0.0, bars=6)
    # Slow down everything after the first two bars; they must not affect the bar length.
    beats = [b if i <= 8 else b + 0.1 * (i - 8) for i, b in enumerate(grid.beats)]
    slow_tail = grid.model_copy(update={"beats": beats, "downbeats": beats[::4]})
    assert build_timeline(slow_tail).bar_samples == 88200


def test_short_grid_falls_back_to_all_beats() -> None:
    grid = make_grid(120, 4, 0.5, bars=1)
    assert build_timeline(grid).bar_samples == 88200


def test_grid_without_downbeats_is_rejected() -> None:
    grid = Grid(bpm=120, beats=[0.0, 0.5], downbeats=[], time_signature="4/4")
    with pytest.raises(TimelineError):
        build_timeline(grid)


def test_grid_with_one_beat_is_rejected() -> None:
    grid = Grid(bpm=120, beats=[0.5], downbeats=[0.5], time_signature="4/4")
    with pytest.raises(TimelineError):
        build_timeline(grid)


def test_snap_to_nearest_downbeat() -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5))  # bars every 2 s: 0.5, 2.5, 4.5, ...
    assert snap_to_downbeat(timeline, 0.0) == 0
    assert snap_to_downbeat(timeline, 2.4) == 1
    assert snap_to_downbeat(timeline, 3.4) == 1
    assert snap_to_downbeat(timeline, 3.6) == 2
    assert snap_to_downbeat(timeline, 999.0) == len(timeline.downbeats) - 1


def test_cue_is_one_bar_before_section() -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5))
    [cue] = section_cues(timeline, [Section(name=SectionName.CHORUS, start=6.5)])
    assert cue.downbeat == timeline.downbeats[3]
    assert cue.cue == timeline.downbeats[2]
    assert cue.downbeat - cue.cue == timeline.bar_samples


def test_first_downbeat_cue_falls_in_the_count_in() -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5))
    [cue] = section_cues(timeline, [Section(name=SectionName.INTRO, start=0.5)])
    assert cue.cue == timeline.first_downbeat - timeline.bar_samples == timeline.count_in_start


def test_cue_uses_actual_previous_downbeat_when_bars_are_uneven() -> None:
    grid = make_grid(120, 4, 0.5)
    downbeats = list(grid.downbeats)
    downbeats[2] += 0.04  # a slightly late bar
    timeline = build_timeline(grid.model_copy(update={"downbeats": downbeats}))
    [cue] = section_cues(timeline, [Section(name=SectionName.BRIDGE, start=6.5)])
    assert cue.cue == timeline.downbeats[2]
    assert cue.downbeat - cue.cue != timeline.bar_samples


def test_uneven_bars_cue_equals_previous_downbeat_not_bar_samples() -> None:
    # Acceptance criterion 3, stated precisely: the cue is the previous detected downbeat.
    grid = make_grid(120, 4, 0.5)
    downbeats = list(grid.downbeats)
    downbeats[3] += 0.03
    timeline = build_timeline(grid.model_copy(update={"downbeats": downbeats}))
    cues = section_cues(
        timeline,
        [
            Section(name=SectionName.VERSE, start=downbeats[3]),
            Section(name=SectionName.CHORUS, start=downbeats[4]),
        ],
    )
    for cue, index in zip(cues, (3, 4), strict=True):
        assert cue.downbeat == timeline.downbeats[index]
        assert cue.cue == timeline.downbeats[index - 1]
    assert cues[0].downbeat - cues[0].cue != timeline.bar_samples


@pytest.mark.parametrize("beats", [[0.5, 0.5, 1.0], [0.5, 1.0, 0.75], [0.5, float("nan"), 1.0]])
def test_degenerate_beats_are_rejected(beats: list[float]) -> None:
    grid = Grid(bpm=120, beats=beats, downbeats=[0.5], time_signature="4/4")
    with pytest.raises(TimelineError, match="beat"):
        build_timeline(grid)


def test_duplicate_or_unsorted_downbeats_are_rejected() -> None:
    grid = make_grid(120, 4, 0.5)
    for downbeats in ([0.5, 0.5], [2.5, 0.5]):
        with pytest.raises(TimelineError, match="downbeats"):
            build_timeline(grid.model_copy(update={"downbeats": downbeats}))


@pytest.mark.parametrize("bars", [0, 3, -1])
def test_count_in_bars_is_validated_when_called_directly(bars: int) -> None:
    with pytest.raises(TimelineError, match="count_in_bars"):
        build_timeline(make_grid(120, 4, 0.5), count_in_bars=bars)


def test_section_outside_the_grid_snaps_to_the_nearest_downbeat() -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5))  # downbeats from 0.5 s to 14.5 s
    [early, late] = section_cues(
        timeline,
        [Section(name=SectionName.INTRO, start=0.0), Section(name=SectionName.TAG, start=99.0)],
    )
    assert early.downbeat == timeline.downbeats[0]
    assert early.cue == timeline.count_in_start
    assert late.downbeat == timeline.downbeats[-1]
    assert late.cue == timeline.downbeats[-2]


@pytest.mark.parametrize("seconds", [-1.0, float("nan"), float("inf")])
def test_snap_rejects_negative_and_non_finite_times(seconds: float) -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5))
    with pytest.raises(TimelineError):
        snap_to_downbeat(timeline, seconds)


def test_cue_before_zero_is_skipped_not_clamped() -> None:
    assert cue_position([50, 100], index=0, bar_samples=88200) is None
    assert cue_position([50, 100], index=1, bar_samples=88200) == 50
    assert cue_position([88200], index=0, bar_samples=88200) == 0
