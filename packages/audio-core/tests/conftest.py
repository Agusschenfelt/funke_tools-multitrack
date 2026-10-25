from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

SINE_AMPLITUDE = 0.5
SINE_RATE = 48000


@pytest.fixture
def sine_wav(tmp_path: Path) -> Path:
    """A 3-second stereo 440 Hz sine at 48 kHz (not 44.1 kHz, to exercise resampling)."""
    t = np.arange(3 * SINE_RATE) / SINE_RATE
    mono = SINE_AMPLITUDE * np.sin(2 * np.pi * 440 * t)
    path = tmp_path / "sine.wav"
    sf.write(str(path), np.stack([mono, mono], axis=1).astype(np.float32), SINE_RATE)
    return path
