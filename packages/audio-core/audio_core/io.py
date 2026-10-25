"""Audio decoding and WAV writing."""

import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from audio_core.constants import CHANNELS, DTYPE, SAMPLE_RATE


class DecodeError(RuntimeError):
    """Raised when ffmpeg cannot decode an input file."""


def decode(path: Path) -> np.ndarray:
    """Decode any ffmpeg-readable file to float32 stereo at 44.1 kHz, shape (2, n_samples)."""
    cmd = [
        "ffmpeg", "-v", "error", "-nostdin",
        "-i", str(path),
        "-f", "f32le", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE),
        "-",
    ]  # fmt: skip
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise DecodeError("ffmpeg executable not found on PATH") from exc
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", errors="replace").strip()[-500:]
        raise DecodeError(f"ffmpeg failed to decode {path} (exit {proc.returncode}): {tail}")
    samples = np.frombuffer(proc.stdout, dtype=np.float32)
    samples = samples[: samples.size - samples.size % CHANNELS]
    return np.ascontiguousarray(samples.reshape(-1, CHANNELS).T, dtype=DTYPE)


def write_wav(
    path: Path, audio: np.ndarray, sample_rate: int = SAMPLE_RATE, subtype: str = "FLOAT"
) -> None:
    """Write audio of shape (channels, samples) to a WAV file."""
    sf.write(str(path), audio.T, sample_rate, subtype=subtype)


def duration_seconds(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> float:
    """Return the duration of audio of shape (channels, samples) in seconds."""
    return audio.shape[-1] / sample_rate
