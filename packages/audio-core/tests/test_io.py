import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from audio_core.constants import SAMPLE_RATE
from audio_core.io import (
    DecodeError,
    decode,
    duration_seconds,
    encode_preview,
    probe_duration,
    write_wav,
)
from tests.conftest import SINE_AMPLITUDE, requires_ffmpeg


@requires_ffmpeg
def test_decode_shape_dtype_and_peak(sine_wav: Path) -> None:
    audio = decode(sine_wav)
    assert audio.dtype == np.float32
    assert audio.shape[0] == 2
    assert abs(audio.shape[1] - 3 * SAMPLE_RATE) <= 2
    assert np.max(np.abs(audio)) == pytest.approx(SINE_AMPLITUDE, abs=0.02)
    assert duration_seconds(audio) == pytest.approx(3.0, abs=0.001)


def test_decode_missing_file_names_the_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.wav"
    with pytest.raises(DecodeError, match="not found") as info:
        decode(missing)
    assert str(missing) in str(info.value)


@requires_ffmpeg
def test_decode_undecodable_file_reports_ffmpeg_failure(tmp_path: Path) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("not audio", encoding="utf-8")
    with pytest.raises(DecodeError, match="ffmpeg failed"):
        decode(bad)


def test_write_wav_round_trip(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    audio = rng.uniform(-0.5, 0.5, size=(2, 1000)).astype(np.float32)
    path = tmp_path / "out.wav"
    write_wav(path, audio)
    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    assert rate == SAMPLE_RATE
    np.testing.assert_array_equal(data.T, audio)


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not on PATH")
def test_probe_duration_reads_the_container_duration(sine_wav: Path) -> None:
    assert probe_duration(sine_wav) == pytest.approx(3.0, abs=0.01)


def test_probe_duration_is_none_for_a_missing_file(tmp_path: Path) -> None:
    assert probe_duration(tmp_path / "missing.wav") is None


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("ffprobe"),
        subprocess.TimeoutExpired("ffprobe", 1),
        subprocess.CompletedProcess([], 1, b"", b"boom"),
        subprocess.CompletedProcess([], 0, b"N/A\n", b""),
        subprocess.CompletedProcess([], 0, b"nan\n", b""),
        subprocess.CompletedProcess([], 0, b"", b""),
    ],
)
def test_probe_duration_falls_back_to_none_on_failure(
    failure: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> object:
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert probe_duration(tmp_path / "x.wav") is None


@requires_ffmpeg
def test_encode_preview_makes_a_small_aac_m4a_with_the_same_length(
    sine_wav: Path, tmp_path: Path
) -> None:
    target = tmp_path / "preview" / "sine.m4a"
    encode_preview(sine_wav, target)
    assert target.stat().st_size < sine_wav.stat().st_size / 4
    original, decoded = decode(sine_wav), decode(target)
    # The edit list hides the encoder delay; at most one frame of padding remains.
    assert 0 <= decoded.shape[-1] - original.shape[-1] < 1024


@requires_ffmpeg
def test_encode_preview_reports_an_unreadable_input(tmp_path: Path) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("not audio", encoding="utf-8")
    with pytest.raises(DecodeError, match="ffmpeg failed to encode"):
        encode_preview(bad, tmp_path / "out.m4a")
