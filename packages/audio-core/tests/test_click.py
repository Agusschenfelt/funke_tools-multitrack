import numpy as np
import pytest

from audio_core.click import (
    ACCENT_PEAK,
    NORMAL_PEAK,
    SUBDIVISION_PEAK,
    click_events,
    click_sample,
    render_click,
)
from audio_core.constants import SAMPLE_RATE
from audio_core.models import Grid, StagePackOptions
from audio_core.timeline import build_timeline

SR = SAMPLE_RATE
SOUNDS = ["classic", "cowbell", "woodblock", "rimshot"]


def make_grid(bpm: float, bpb: int, t0: float, bars: int = 8, signature: str | None = None) -> Grid:
    interval = 60.0 / bpm
    beats = [t0 + i * interval for i in range(bars * bpb)]
    return Grid(
        bpm=bpm,
        beats=beats,
        downbeats=beats[::bpb],
        time_signature=signature or f"{bpb}/4",
    )


def options(**kwargs: object) -> StagePackOptions:
    return StagePackOptions(destination="daw", **kwargs)  # type: ignore[arg-type]


def total_for(timeline_end: int) -> int:
    return timeline_end + SR


def test_onsets_match_shifted_grid_exactly() -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5), count_in_bars=1)
    total = total_for(timeline.beats[-1])
    events = click_events(timeline, total, options())
    expected = sorted(timeline.count_in_beats + timeline.beats)
    assert [e.sample for e in events] == expected
    # Brief test 2: well inside 10 ms (here exactly 0 samples).
    tolerance = round(0.010 * SR)
    assert all(abs(e.sample - s) <= tolerance for e, s in zip(events, expected, strict=True))


def test_audio_onset_is_at_event_sample() -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5), count_in_bars=1)
    total = total_for(timeline.beats[-1])
    audio = render_click(timeline, total, options())
    for event in click_events(timeline, total, options()):
        assert audio[event.sample] != 0.0
        assert audio[event.sample - 1] == 0.0


def test_accents_only_on_downbeats_and_count_in_bar_starts() -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5), count_in_bars=2)
    total = total_for(timeline.beats[-1])
    events = click_events(timeline, total, options())
    accented = {e.sample for e in events if e.accent}
    count_in_starts = {timeline.count_in_beats[0], timeline.count_in_beats[4]}
    assert accented == count_in_starts | set(timeline.downbeats)


def test_accent_is_louder_than_normal_in_audio() -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5), count_in_bars=1)
    total = total_for(timeline.beats[-1])
    audio = render_click(timeline, total, options())
    window = SR // 20
    peaks = [np.abs(audio[s : s + window]).max() for s in timeline.count_in_beats]
    assert peaks[0] == pytest.approx(ACCENT_PEAK, rel=1e-3)
    assert all(p == pytest.approx(NORMAL_PEAK, rel=1e-3) for p in peaks[1:])


def test_eighth_subdivision_adds_one_soft_click_between_beats() -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5), count_in_bars=1)
    total = total_for(timeline.beats[-1])
    events = click_events(timeline, total, options(subdivision="eighth"))
    quarters = [e for e in events if not e.subdivision]
    subs = [e for e in events if e.subdivision]
    assert len(subs) == len(quarters)
    assert not any(e.accent for e in subs)
    for a, b in zip(quarters, quarters[1:], strict=False):
        between = [e.sample for e in subs if a.sample < e.sample < b.sample]
        assert between == [(a.sample + b.sample) // 2]
    # Last beat uses the local interval (22050 samples at 120 BPM).
    assert subs[-1].sample == quarters[-1].sample + 11025

    audio = render_click(timeline, total, options(subdivision="eighth"))
    peak = np.abs(audio[subs[0].sample : subs[0].sample + SR // 20]).max()
    assert peak == pytest.approx(SUBDIVISION_PEAK, rel=1e-3)


def test_straight_grid_is_evenly_spaced_at_mean_bpm() -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5), count_in_bars=1)
    total = total_for(timeline.beats[-1])
    events = click_events(timeline, total, options(straight_grid=True))
    onsets = np.array([e.sample for e in events])
    assert np.all(np.abs(np.diff(onsets) - 22050) <= 1)
    assert onsets[0] == timeline.count_in_beats[0]
    assert timeline.first_downbeat in onsets
    # Steady synthetic grid: straight clicks match the detected beats within tolerance.
    for sample in timeline.beats:
        assert np.abs(onsets - sample).min() <= round(0.010 * SR)


def test_straight_grid_quantizes_a_wobbly_grid_and_keeps_count_in() -> None:
    grid = make_grid(120, 4, 0.5)
    rng = np.random.default_rng(3)
    grid.beats = [b + float(rng.uniform(-0.02, 0.02)) for b in grid.beats]
    grid.downbeats = grid.beats[::4]
    timeline = build_timeline(grid, count_in_bars=1)
    total = total_for(timeline.beats[-1])
    straight = click_events(timeline, total, options(straight_grid=True))
    followed = click_events(timeline, total, options())
    count_in = set(timeline.count_in_beats)
    assert {e.sample for e in straight} >= count_in
    assert {e.sample for e in followed} >= count_in
    after = [e.sample for e in straight if e.sample >= timeline.first_downbeat]
    steps = np.diff(after)
    assert steps.max() - steps.min() <= 1
    assert after[0] == timeline.first_downbeat
    # Accents every beats_per_bar clicks from the first downbeat.
    flags = [e.accent for e in straight if e.sample >= timeline.first_downbeat]
    assert flags[:8] == [True, False, False, False, True, False, False, False]


@pytest.mark.parametrize("name", SOUNDS)
def test_all_sounds_render_finite_and_bounded(name: str) -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5), count_in_bars=1)
    total = total_for(timeline.beats[-1])
    audio = render_click(timeline, total, options(click_sound=name, subdivision="eighth"))
    assert audio.dtype == np.float32
    assert audio.shape == (total,)
    assert np.isfinite(audio).all()
    assert np.abs(audio).max() <= 1.0
    assert np.abs(audio).max() == pytest.approx(ACCENT_PEAK, rel=1e-3)


@pytest.mark.parametrize("name", SOUNDS)
def test_sounds_are_short_and_start_at_first_sample(name: str) -> None:
    accent = click_sample(name, accent=True)
    normal = click_sample(name, accent=False)
    assert len(accent) <= round(0.060 * SR)
    assert accent[0] != 0.0
    assert not np.array_equal(accent, normal)


def test_output_length_exact_and_late_clicks_truncated() -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5), count_in_bars=1)
    # End one sample after a beat: the click is cut to a single sample, never wrapped.
    total = timeline.beats[3] + 1
    audio = render_click(timeline, total, options())
    assert audio.shape == (total,)
    assert audio[-1] != 0.0
    assert all(e.sample < total for e in click_events(timeline, total, options()))


def test_empty_when_total_is_zero() -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5), count_in_bars=1)
    assert render_click(timeline, 0, options()).shape == (0,)


def test_three_four_accents_every_third_beat() -> None:
    timeline = build_timeline(make_grid(90, 3, 1.0), count_in_bars=1)
    total = total_for(timeline.beats[-1])
    events = click_events(timeline, total, options())
    assert [e.accent for e in events][:6] == [True, False, False, True, False, False]
    assert {e.sample for e in events if e.accent} == {
        timeline.count_in_beats[0],
        *timeline.downbeats,
    }
    straight = click_events(timeline, total, options(straight_grid=True))
    assert [e.accent for e in straight if e.sample >= timeline.first_downbeat][:6] == [
        True,
        False,
        False,
        True,
        False,
        False,
    ]


def test_six_eight_uses_six_clicks_per_bar() -> None:
    timeline = build_timeline(make_grid(180, 6, 0.0, signature="6/8"), count_in_bars=1)
    total = total_for(timeline.beats[-1])
    events = click_events(timeline, total, options())
    assert len(timeline.count_in_beats) == 6
    assert [e.accent for e in events][:12] == [True, False, False, False, False, False] * 2
    assert {e.sample for e in events if e.accent} == {
        timeline.count_in_beats[0],
        *timeline.downbeats,
    }


def test_pickup_beats_inside_count_in_do_not_double_click() -> None:
    # Pickup beats at 0.0 and 0.5 s before the first downbeat at 1.0 s; 120 BPM, 4/4.
    grid = Grid(
        bpm=120,
        beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5],
        downbeats=[1.0, 3.0],
        time_signature="4/4",
    )
    timeline = build_timeline(grid, count_in_bars=1)
    total = total_for(timeline.beats[-1])
    samples = [e.sample for e in click_events(timeline, total, options())]
    assert len(samples) == len(set(samples))
    assert np.all(np.diff(samples) >= 22050 - 1)


def test_accent_survives_beat_and_downbeat_rounding_differences() -> None:
    # Beats sit 20 microseconds off the downbeats: they round to a different sample (+1), so an
    # exact-equality match would lose every accent.
    base = make_grid(120, 4, 1.0, bars=3)
    grid = Grid(
        bpm=120,
        beats=[b + 0.00002 for b in base.beats],
        downbeats=base.downbeats,
        time_signature="4/4",
    )
    timeline = build_timeline(grid, count_in_bars=1)
    assert set(timeline.beats).isdisjoint(timeline.downbeats)
    events = click_events(timeline, total_for(timeline.beats[-1]), options())
    accented = {e.sample for e in events if e.accent}
    in_grid = {s for s in timeline.beats if s >= timeline.first_downbeat}
    assert {s for s in in_grid if s - 1 in set(timeline.downbeats)} <= accented
    assert len([e for e in events if e.accent and e.sample >= timeline.first_downbeat]) == 3
