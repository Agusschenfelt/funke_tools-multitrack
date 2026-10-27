import shutil
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pytest
import soundfile as sf

SINE_AMPLITUDE = 0.5
SINE_RATE = 48000
FIXTURE_RATE = 44100

requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


class ClickTrack(NamedTuple):
    path: Path
    bpm: float
    beat_times: np.ndarray
    downbeat_times: np.ndarray


def _write_stereo(path: Path, mono: np.ndarray, rate: int) -> None:
    sf.write(str(path), np.stack([mono, mono], axis=1).astype(np.float32), rate)


@pytest.fixture
def sine_wav(tmp_path: Path) -> Path:
    """A 3-second stereo 440 Hz sine at 48 kHz (not 44.1 kHz, to exercise resampling)."""
    t = np.arange(3 * SINE_RATE) / SINE_RATE
    mono = SINE_AMPLITUDE * np.sin(2 * np.pi * 440 * t)
    path = tmp_path / "sine.wav"
    _write_stereo(path, mono, SINE_RATE)
    return path


@pytest.fixture
def sine_minus20_wav(tmp_path: Path) -> Path:
    """A 10-second stereo 440 Hz sine with a peak of -20 dBFS at 44.1 kHz."""
    t = np.arange(10 * FIXTURE_RATE) / FIXTURE_RATE
    mono = 0.1 * np.sin(2 * np.pi * 440 * t)
    path = tmp_path / "sine_minus20.wav"
    _write_stereo(path, mono, FIXTURE_RATE)
    return path


@pytest.fixture
def c_major_wav(tmp_path: Path) -> Path:
    """Eight seconds of a C major chord (C4, E4, G4 plus the C5 octave), stereo, 44.1 kHz."""
    t = np.arange(8 * FIXTURE_RATE) / FIXTURE_RATE
    freqs = [261.63, 329.63, 392.00, 523.25]
    mono = sum(np.sin(2 * np.pi * f * t) for f in freqs) * 0.15
    path = tmp_path / "c_major.wav"
    _write_stereo(path, mono, FIXTURE_RATE)
    return path


def _write_click_track(path: Path, bpm: float, beats_per_bar: int, seconds: int) -> ClickTrack:
    """Decaying 1 kHz bursts from 0 s to ``seconds`` (inclusive), louder on downbeats.

    The file is padded 0.1 s past the last click so the model can see it.
    """
    interval = 60.0 / bpm
    n = int((seconds + 0.1) * FIXTURE_RATE)
    mono = np.zeros(n)
    click_len = int(0.05 * FIXTURE_RATE)
    tc = np.arange(click_len) / FIXTURE_RATE
    burst = np.sin(2 * np.pi * 1000 * tc) * np.exp(-tc / 0.01)
    beat_times = np.arange(0.0, seconds + 0.01, interval)
    for i, bt in enumerate(beat_times):
        start = int(round(bt * FIXTURE_RATE))
        gain = 0.9 if i % beats_per_bar == 0 else 0.5
        end = min(start + click_len, n)
        mono[start:end] += gain * burst[: end - start]
    _write_stereo(path, mono, FIXTURE_RATE)
    return ClickTrack(path, bpm, beat_times, beat_times[::beats_per_bar])


@pytest.fixture
def click_track_wav(tmp_path: Path) -> ClickTrack:
    """120 BPM in 4/4, clicks from 0 s to 20 s (inclusive, 41 beats)."""
    return _write_click_track(tmp_path / "click_track.wav", 120.0, 4, 20)


@pytest.fixture
def click_track_34_wav(tmp_path: Path) -> ClickTrack:
    """90 BPM in 3/4, clicks from 0 s to 12 s (inclusive, 19 beats)."""
    return _write_click_track(tmp_path / "click_track_34.wav", 90.0, 3, 12)
