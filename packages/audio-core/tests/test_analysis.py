import numpy as np
import pytest

from audio_core.analysis import (
    AnalysisError,
    camelot_code,
    compatible_codes,
    compute_bpm,
    estimate_key_librosa,
    infer_time_signature,
    measure_loudness,
    resolve_key_backend,
    true_peak,
)
from audio_core.analysis import analyze as run_analyze
from audio_core.constants import SAMPLE_RATE
from audio_core.io import decode
from audio_core.models import Analysis
from tests.conftest import ClickTrack, requires_ffmpeg


@pytest.mark.parametrize(
    ("pitch_class", "mode", "expected"),
    [(0, "major", "8B"), (9, "minor", "8A"), (7, "major", "9B"), (6, "minor", "11A"),
     (0, "minor", "5A"), (11, "major", "1B")],
)  # fmt: skip
def test_camelot_mapping(pitch_class: int, mode: str, expected: str) -> None:
    assert camelot_code(pitch_class, mode) == expected


def test_compatible_codes_wrap_around() -> None:
    assert compatible_codes("8A") == ["8B", "7A", "9A"]
    assert compatible_codes("1B") == ["1A", "12B", "2B"]
    assert compatible_codes("12A") == ["12B", "11A", "1A"]


def test_bpm_is_median_of_intervals() -> None:
    beats = np.array([0.0, 0.5, 1.0, 1.5, 2.6])  # one outlier interval
    assert compute_bpm(beats) == 120.0


def test_bpm_requires_two_beats() -> None:
    with pytest.raises(AnalysisError):
        compute_bpm(np.array([1.0]))


@pytest.mark.parametrize(("per_bar", "expected"), [(4, "4/4"), (3, "3/4"), (6, "6/8"), (2, "2/4")])
def test_time_signature_from_downbeat_spacing(per_bar: int, expected: str) -> None:
    beats = np.arange(0, 8 * per_bar) * 0.5
    signature, notes = infer_time_signature(beats, beats[::per_bar])
    assert signature == expected
    assert notes == []


def test_unsupported_meter_defaults_with_note() -> None:
    beats = np.arange(0, 35) * 0.5
    signature, notes = infer_time_signature(beats, beats[::7])
    assert signature == "4/4"
    assert len(notes) == 1
    assert "7 beats per bar" in notes[0]


@requires_ffmpeg
def test_key_fallback_detects_c_major(c_major_wav) -> None:
    info = estimate_key_librosa(decode(c_major_wav))
    assert (info.key, info.mode, info.camelot) == ("C", "major", "8B")
    assert "8A" in info.compatible


@requires_ffmpeg
def test_loudness_of_minus_20_dbfs_sine(sine_minus20_wav) -> None:
    """A stereo 440 Hz sine peaking at -20 dBFS measures about -20 LUFS (K-weighting is near
    unity at 440 Hz and identical channels add 3 dB); tolerance is 1.5 LU."""
    loudness = measure_loudness(decode(sine_minus20_wav))
    assert loudness.integrated_lufs == pytest.approx(-20.0, abs=1.5)
    assert loudness.true_peak_dbtp == pytest.approx(-20.0, abs=0.5)


def test_key_of_silence_is_unknown() -> None:
    info = estimate_key_librosa(np.zeros((2, 4 * SAMPLE_RATE), dtype=np.float32))
    assert (info.key, info.mode, info.camelot) == ("unknown", "unknown", "")
    assert info.compatible == []
    assert info.note


def test_unknown_key_round_trips_through_analysis_model() -> None:
    info = estimate_key_librosa(np.zeros((2, SAMPLE_RATE), dtype=np.float32))
    result = Analysis(
        source="x", duration=1.0, sample_rate=SAMPLE_RATE, grid=None, key=info, loudness=None,
        models={},
    )  # fmt: skip
    assert Analysis.model_validate_json(result.model_dump_json()).key == info


def test_essentia_backend_unavailable_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("audio_core.analysis._essentia_available", lambda: False)
    with pytest.raises(AnalysisError, match="essentia"):
        resolve_key_backend("essentia")
    assert resolve_key_backend("auto") == "librosa"
    assert resolve_key_backend("librosa") == "librosa"


def test_unknown_key_backend_raises() -> None:
    with pytest.raises(AnalysisError, match="unknown key backend"):
        resolve_key_backend("nope")  # type: ignore[arg-type]


def test_chunked_true_peak_matches_single_pass() -> None:
    """A 25 s signal spans three 10 s blocks; the result must match one full-length pass."""
    from scipy.signal import resample_poly

    rng = np.random.default_rng(0)
    t = np.arange(25 * SAMPLE_RATE) / SAMPLE_RATE
    audio = (0.4 * np.sin(2 * np.pi * 997 * t) + 0.1 * rng.standard_normal(t.size)).astype(
        np.float32
    )
    audio = np.stack([audio, audio * 0.8])
    expected = float(np.max(np.abs(resample_poly(audio, 4, 1, axis=1))))
    got = true_peak(audio)
    assert abs(20 * np.log10(got) - 20 * np.log10(expected)) < 0.01


def test_loudness_of_silence_is_finite() -> None:
    loudness = measure_loudness(np.zeros((2, 44100), dtype=np.float32))
    assert np.isfinite(loudness.integrated_lufs)
    assert np.isfinite(loudness.true_peak_dbtp)


@pytest.mark.slow
@requires_ffmpeg
def test_click_track_grid_and_models(click_track_wav: ClickTrack) -> None:
    """Runs beat_this final0 on CPU; downloads the checkpoint on first run."""
    result = run_analyze(decode(click_track_wav.path), "click.wav")
    assert result.grid is not None
    assert result.grid.bpm == pytest.approx(click_track_wav.bpm, abs=0.5)
    assert result.grid.time_signature == "4/4"

    detected = np.array(result.grid.beats)
    truth = click_track_wav.beat_times
    matched = sum(np.min(np.abs(detected - t)) <= 0.010 for t in truth)
    assert matched / len(truth) >= 0.9
    assert all(np.min(np.abs(truth - d)) <= 0.010 for d in detected)

    assert set(result.models) == {"beats", "key", "loudness"}
    assert result.models["beats"].name == "beat_this"
    assert result.models["beats"].source == "final0 checkpoint"


@requires_ffmpeg
def test_three_four_grid_is_reported_as_three_four(
    click_track_34_wav: ClickTrack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the true 3/4 grid injected, analyze must report 3/4 (not the 4/4 default)."""
    monkeypatch.setattr(
        "audio_core.analysis.detect_beats",
        lambda audio, **_: (click_track_34_wav.beat_times, click_track_34_wav.downbeat_times),
    )
    result = run_analyze(decode(click_track_34_wav.path), "click_34.wav")
    assert result.grid is not None
    assert result.grid.bpm == pytest.approx(90.0, abs=0.5)
    assert result.grid.time_signature == "3/4"
    assert result.grid.notes == []


@pytest.mark.slow
@pytest.mark.xfail(
    reason="beat_this (without the DBN) marks nearly every click as a downbeat on synthetic "
    "3/4 clicks, so the meter falls back to 4/4; real music is expected to work",
    strict=False,
)
@requires_ffmpeg
def test_three_four_click_track_model_detection(click_track_34_wav: ClickTrack) -> None:
    """Runs beat_this on a 90 BPM 3/4 click track and expects 3/4 (known model limitation)."""
    result = run_analyze(decode(click_track_34_wav.path), "click_34.wav")
    assert result.grid is not None
    assert result.grid.time_signature == "3/4"
