import numpy as np

from audio_core.analysis import build_grid
from audio_core.gridfix import drop_extrapolated, remove_outlier_beats
from audio_core.models import Analysis, Grid


def steady(start: float, count: int, interval: float = 0.5) -> np.ndarray:
    return start + interval * np.arange(count)


def test_beatless_lead_in_is_extrapolated_back_to_zero() -> None:
    beats = steady(30.2, 64)
    downbeats = beats[::4]
    grid = build_grid(beats, downbeats)
    assert grid.extrapolated_until == 30.2
    assert grid.beats[0] < 0.5
    assert np.allclose(np.diff(grid.beats), 0.5, atol=1e-3)
    assert grid.bpm == 120.0
    # Downbeat phase continues: every 4th beat, and the detected downbeat stays a downbeat.
    assert np.allclose(np.diff(grid.downbeats), 2.0, atol=1e-3)
    assert 30.2 in grid.downbeats
    first_down = grid.beats.index(grid.downbeats[0])
    assert first_down < 4
    detected = [b for b in grid.beats if b >= 30.2 - 1e-3]
    assert np.allclose(detected, beats, atol=1e-3)


def test_downbeat_phase_follows_a_pickup() -> None:
    beats = steady(20.0, 64)
    downbeats = beats[2::4]  # first detected downbeat is the third beat
    grid = build_grid(beats, downbeats)
    index = {round(b, 3): i for i, b in enumerate(grid.beats)}
    positions = {index[round(d, 3)] % 4 for d in grid.downbeats}
    assert len(positions) == 1
    assert grid.downbeats[0] < 2.0


def test_no_lead_in_means_no_change() -> None:
    beats = steady(0.4, 64)
    grid = build_grid(beats, beats[::4])
    assert grid.extrapolated_until is None
    assert len(grid.beats) == 64
    short = build_grid(steady(0.8, 64), steady(0.8, 64)[::4])  # under two bars
    assert short.extrapolated_until is None


def test_evidence_outlier_is_removed_and_downbeats_stay_beats() -> None:
    body = steady(57.08, 40)
    beats = np.concatenate([[55.22, 56.26, 56.48], body])
    downbeats = np.array([55.22, 57.08, 59.08])
    cleaned, cleaned_down, removed = remove_outlier_beats(beats, downbeats)
    assert removed == 1
    # The beat nearer to where the steady run puts it (57.08 - 0.5 = 56.58) stays.
    assert 56.48 in cleaned and 56.26 not in cleaned
    assert all(np.isclose(cleaned, d).any() for d in cleaned_down)


def test_removed_downbeat_moves_to_the_kept_beat() -> None:
    beats = np.concatenate([[10.0, 10.5, 11.0], [11.2], steady(11.5, 20)])
    downbeats = np.array([11.2, 13.5])
    cleaned, cleaned_down, removed = remove_outlier_beats(beats, downbeats)
    assert removed == 1
    assert all(np.isclose(cleaned, d).any() for d in cleaned_down)
    assert len(cleaned_down) == 2


def test_genuine_tempo_change_is_untouched() -> None:
    first = steady(0.0, 20, 0.5)
    second = steady(first[-1] + 0.25, 40, 0.25)  # tempo doubles: a run of short intervals
    beats = np.concatenate([first, second])
    cleaned, _, removed = remove_outlier_beats(beats, beats[::4])
    assert removed == 0
    assert cleaned.size == beats.size


def test_postprocess_can_be_disabled() -> None:
    beats = steady(30.0, 40)
    grid = build_grid(beats, beats[::4], postprocess=False)
    assert grid.extrapolated_until is None
    assert len(grid.beats) == 40


def test_drop_extrapolated_restores_the_detected_grid() -> None:
    beats = steady(30.0, 40)
    grid = build_grid(beats, beats[::4])
    plain = drop_extrapolated(grid)
    assert plain.extrapolated_until is None
    assert np.allclose(plain.beats, beats, atol=1e-3)
    assert np.allclose(plain.downbeats, beats[::4], atol=1e-3)
    assert drop_extrapolated(plain) is plain


def test_stored_analysis_without_the_field_still_validates() -> None:
    raw = {
        "source": "x.wav",
        "duration": 4.0,
        "sample_rate": 44100,
        "grid": {"bpm": 120, "beats": [0.5, 1.0], "downbeats": [0.5], "time_signature": "4/4"},
        "key": None,
        "loudness": None,
        "models": {},
    }
    analysis = Analysis.model_validate(raw)
    assert isinstance(analysis.grid, Grid)
    assert analysis.grid.extrapolated_until is None
