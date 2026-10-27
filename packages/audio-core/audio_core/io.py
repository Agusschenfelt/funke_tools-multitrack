"""Audio decoding and WAV writing."""

import math
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from audio_core.constants import CHANNELS, DTYPE, PREVIEW_BITRATE_KBPS, SAMPLE_RATE


class DecodeError(RuntimeError):
    """Raised when ffmpeg cannot decode an input file."""


DEFAULT_DECODE_TIMEOUT = 600.0


def decode(path: Path, timeout: float = DEFAULT_DECODE_TIMEOUT) -> np.ndarray:
    """Decode any ffmpeg-readable file to float32 stereo at 44.1 kHz, shape (2, n_samples).

    The whole decoded stream is buffered in memory. That is acceptable because the product caps
    inputs at 10 minutes (about 212 MB of float32 stereo at 44.1 kHz); callers enforce that cap
    with ``probe_duration`` before decoding.
    """
    if not Path(path).is_file():
        raise DecodeError(f"input file not found: {path}")
    cmd = [
        "ffmpeg", "-v", "error", "-nostdin",
        "-i", str(path),
        "-f", "f32le", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE),
        "-",
    ]  # fmt: skip
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False, timeout=timeout)
    except FileNotFoundError as exc:
        raise DecodeError("ffmpeg executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise DecodeError(f"ffmpeg timed out after {timeout:g} s decoding {path}") from exc
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", errors="replace").strip()[-500:]
        raise DecodeError(f"ffmpeg failed to decode {path} (exit {proc.returncode}): {tail}")
    samples = np.frombuffer(proc.stdout, dtype=np.float32)
    # Drop a trailing partial frame (fewer samples than channels) from a truncated stream.
    samples = samples[: samples.size - samples.size % CHANNELS]
    return np.ascontiguousarray(samples.reshape(-1, CHANNELS).T, dtype=DTYPE)


DEFAULT_PROBE_TIMEOUT = 15.0


def probe_duration(path: Path, timeout: float = DEFAULT_PROBE_TIMEOUT) -> float | None:
    """Container duration in seconds via ``ffprobe``, without decoding; ``None`` if unknown.

    Any failure (ffprobe missing, timeout, non-zero exit, unparsable or non-finite output) returns
    ``None`` so the caller can fall back to the decoded length.
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]  # fmt: skip
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        value = float(proc.stdout.decode("utf-8", errors="replace").strip().splitlines()[0])
    except (ValueError, IndexError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def write_wav(
    path: Path, audio: np.ndarray, sample_rate: int = SAMPLE_RATE, subtype: str = "FLOAT"
) -> None:
    """Write audio of shape (channels, samples) to a WAV file."""
    sf.write(str(path), audio.T, sample_rate, subtype=subtype)


def duration_seconds(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> float:
    """Return the duration of audio of shape (channels, samples) in seconds."""
    return audio.shape[-1] / sample_rate


def encode_preview(
    source: Path,
    target: Path,
    bitrate_kbps: int = PREVIEW_BITRATE_KBPS,
    timeout: float = DEFAULT_DECODE_TIMEOUT,
) -> None:
    """Encode an audio file to AAC-LC stereo 44.1 kHz in an ``.m4a`` container with ffmpeg.

    ffmpeg's built-in ``aac`` encoder is used (no external library). The mp4 muxer writes the
    edit list that hides the encoder delay, so decoders that honor it return the original sample
    count. ``+faststart`` keeps the header at the front for streaming.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-v", "error", "-nostdin", "-y",
        "-i", str(source),
        "-vn", "-c:a", "aac", "-b:a", f"{bitrate_kbps}k",
        "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE),
        "-movflags", "+faststart",
        str(target),
    ]  # fmt: skip
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False, timeout=timeout)
    except FileNotFoundError as exc:
        raise DecodeError("ffmpeg executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise DecodeError(f"ffmpeg timed out after {timeout:g} s encoding {source}") from exc
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", errors="replace").strip()[-500:]
        raise DecodeError(f"ffmpeg failed to encode {source} (exit {proc.returncode}): {tail}")
