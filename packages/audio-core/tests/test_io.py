from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from audio_core.constants import SAMPLE_RATE
from audio_core.io import DecodeError, decode, duration_seconds, write_wav
from tests.conftest import SINE_AMPLITUDE


def test_decode_shape_dtype_and_peak(sine_wav: Path) -> None:
    audio = decode(sine_wav)
    assert audio.dtype == np.float32
    assert audio.shape[0] == 2
    assert abs(audio.shape[1] - 3 * SAMPLE_RATE) <= 2
    assert np.max(np.abs(audio)) == pytest.approx(SINE_AMPLITUDE, abs=0.02)
    assert duration_seconds(audio) == pytest.approx(3.0, abs=0.001)


def test_decode_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(DecodeError):
        decode(tmp_path / "missing.wav")


def test_write_wav_round_trip(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    audio = rng.uniform(-0.5, 0.5, size=(2, 1000)).astype(np.float32)
    path = tmp_path / "out.wav"
    write_wav(path, audio)
    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    assert rate == SAMPLE_RATE
    np.testing.assert_array_equal(data.T, audio)
