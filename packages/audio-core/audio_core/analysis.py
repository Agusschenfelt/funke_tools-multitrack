"""Tempo grid, key and loudness analysis.

Beats and downbeats come from ``beat_this`` (CPJKU, MIT, checkpoint ``final0``). Key detection
uses Essentia's ``KeyExtractor`` when ``essentia`` is importable (optional extra, for example in
the Linux worker image) and otherwise falls back to librosa chroma correlated against the
Krumhansl-Schmuckler profiles. Loudness uses ``pyloudnorm`` (ITU-R BS.1770) plus a 4x
oversampled true-peak estimate.

Heavy imports (torch, beat_this, librosa) stay inside the functions that need them so the CLI
``--help`` and the I/O tests remain fast.
"""

from dataclasses import dataclass
from importlib import metadata
from typing import Literal

import numpy as np

from audio_core.constants import SAMPLE_RATE
from audio_core.extras import MissingExtraError, require
from audio_core.gridfix import (
    GRID_POSTPROCESS_VERSION,
    extrapolate_lead_in,
    remove_outlier_beats,
)
from audio_core.models import Analysis, Grid, KeyInfo, Loudness, ModelVersion

BEAT_MODEL = "final0"
TRUE_PEAK_OVERSAMPLING = 4
SILENCE_LUFS = -70.0
SILENCE_DBTP = -120.0
# True peak is computed in blocks so peak memory stays bounded for long inputs.
TRUE_PEAK_BLOCK_SECONDS = 10
TRUE_PEAK_OVERLAP_SAMPLES = 512
# Chroma vectors with a standard deviation below this are treated as constant (silence).
CHROMA_FLATNESS_EPSILON = 1e-6

KeyBackend = Literal["auto", "essentia", "librosa"]
KEY_BACKENDS = ("auto", "essentia", "librosa")

PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}

# Krumhansl-Kessler probe-tone profiles, index 0 = tonic.
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

_BEATS_PER_BAR_TO_SIGNATURE = {4: "4/4", 3: "3/4", 6: "6/8", 2: "2/4"}


class AnalysisError(RuntimeError):
    """Raised when an analysis step cannot produce a result."""


@dataclass(frozen=True)
class AnalyzeOptions:
    beat_checkpoint: str = BEAT_MODEL
    device: str = "cpu"
    key_backend: KeyBackend = "auto"


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unknown"


def to_mono(audio: np.ndarray) -> np.ndarray:
    """Average channels of audio shaped (channels, samples) into a 1-D float32 array."""
    return audio.mean(axis=0, dtype=np.float32)


# --- Beats -------------------------------------------------------------------------------


def detect_beats(
    audio: np.ndarray, *, checkpoint: str = BEAT_MODEL, device: str = "cpu"
) -> tuple[np.ndarray, np.ndarray]:
    """Return (beat_times, downbeat_times) in seconds using beat_this."""
    try:
        Audio2Beats = require("beat_this.inference").Audio2Beats  # noqa: N806

        tracker = Audio2Beats(checkpoint_path=checkpoint, device=device, dbn=False)
        beats, downbeats = tracker(to_mono(audio), SAMPLE_RATE)
    except MissingExtraError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface any model/download failure uniformly
        raise AnalysisError(f"beat tracking failed: {exc}") from exc
    return np.asarray(beats, dtype=np.float64), np.asarray(downbeats, dtype=np.float64)


def compute_bpm(beats: np.ndarray) -> float:
    """Median inter-beat interval converted to BPM, rounded to 2 decimals."""
    if beats.size < 2:
        raise AnalysisError("at least two beats are required to estimate tempo")
    median_interval = float(np.median(np.diff(beats)))
    return round(60.0 / median_interval, 2)


def infer_time_signature(beats: np.ndarray, downbeats: np.ndarray) -> tuple[str, list[str]]:
    """Infer the time signature from the median beat count between consecutive downbeats.

    Returns the signature and a list of warning notes. Unsupported meters map to "4/4".
    """
    if downbeats.size < 2:
        return "4/4", ["fewer than two downbeats detected; time signature defaulted to 4/4"]
    # Index of each downbeat in the beat sequence; the difference is the beats per bar.
    positions = np.searchsorted(beats, downbeats - 1e-3)
    beats_per_bar = int(np.median(np.diff(positions)))
    signature = _BEATS_PER_BAR_TO_SIGNATURE.get(beats_per_bar)
    if signature is None:
        return "4/4", [
            f"unsupported meter with {beats_per_bar} beats per bar; time signature defaulted to 4/4"
        ]
    return signature, []


def build_grid(beats: np.ndarray, downbeats: np.ndarray, *, postprocess: bool = True) -> Grid:
    """Grid from detected beats; by default also drops outlier beats and extrapolates a lead-in."""
    removed = 0
    if postprocess:
        beats, downbeats, removed = remove_outlier_beats(beats, downbeats)
    signature, notes = infer_time_signature(beats, downbeats)
    if removed:
        notes = [*notes, f"removed {removed} outlier beat{'s' if removed != 1 else ''}"]
    grid = Grid(
        bpm=compute_bpm(beats),
        beats=[round(float(t), 4) for t in beats],
        downbeats=[round(float(t), 4) for t in downbeats],
        time_signature=signature,
        notes=notes,
    )
    if postprocess and downbeats.size:
        per_bar = int(signature.split("/")[0])
        grid = extrapolate_lead_in(grid, per_bar)
    return grid


# --- Key ---------------------------------------------------------------------------------


def camelot_code(pitch_class: int, mode: str) -> str:
    """Camelot wheel code: 8B = C major, 8A = A minor (its relative minor)."""
    major_pc = pitch_class if mode == "major" else (pitch_class + 3) % 12
    number = (8 + 7 * major_pc - 1) % 12 + 1
    return f"{number}{'B' if mode == 'major' else 'A'}"


def compatible_codes(camelot: str) -> list[str]:
    """Same number with the other letter, and the neighbouring numbers on the same letter."""
    number, letter = int(camelot[:-1]), camelot[-1]
    other = "A" if letter == "B" else "B"
    down = (number - 2) % 12 + 1
    up = number % 12 + 1
    return [f"{number}{other}", f"{down}{letter}", f"{up}{letter}"]


def key_info(pitch_class: int, mode: str) -> KeyInfo:
    code = camelot_code(pitch_class, mode)
    return KeyInfo(
        key=PITCH_CLASSES[pitch_class],
        mode=mode,
        camelot=code,
        compatible=compatible_codes(code),
    )


def unknown_key(note: str) -> KeyInfo:
    """Result for inputs without a determinable key."""
    return KeyInfo(key="unknown", mode="unknown", camelot="", compatible=[], note=note)


def estimate_key_librosa(audio: np.ndarray) -> KeyInfo:
    """Krumhansl-Schmuckler key estimate from time-averaged CQT chroma."""
    librosa = require("librosa")

    chroma = librosa.feature.chroma_cqt(y=to_mono(audio), sr=SAMPLE_RATE).mean(axis=1)
    if not np.all(np.isfinite(chroma)) or float(np.std(chroma)) < CHROMA_FLATNESS_EPSILON:
        return unknown_key("chroma vector is constant (silence or no tonal content)")
    best_score, best = -np.inf, None
    for mode, profile in (("major", _MAJOR_PROFILE), ("minor", _MINOR_PROFILE)):
        for tonic in range(12):
            score = float(np.corrcoef(chroma, np.roll(profile, tonic))[0, 1])
            if np.isfinite(score) and score > best_score:
                best_score, best = score, (tonic, mode)
    if best is None:
        return unknown_key("all key-profile correlations were undefined")
    return key_info(*best)


def estimate_key_essentia(audio: np.ndarray) -> KeyInfo:
    """Key estimate from Essentia's KeyExtractor. Raises ImportError if unavailable."""
    import essentia.standard as es

    key, scale, _strength = es.KeyExtractor(sampleRate=SAMPLE_RATE)(to_mono(audio))
    name = _FLAT_TO_SHARP.get(key, key)
    if name not in PITCH_CLASSES or scale not in ("major", "minor"):
        raise AnalysisError(f"unexpected Essentia key output: {key} {scale}")
    return key_info(PITCH_CLASSES.index(name), scale)


def _essentia_available() -> bool:
    try:
        import essentia  # noqa: F401
    except ImportError:
        return False
    return True


def resolve_key_backend(backend: KeyBackend = "auto") -> Literal["essentia", "librosa"]:
    """Map the requested backend to the one that will run, failing clearly if unavailable."""
    if backend not in KEY_BACKENDS:
        raise AnalysisError(f"unknown key backend {backend!r}; choose one of {list(KEY_BACKENDS)}")
    if backend == "librosa":
        return "librosa"
    if _essentia_available():
        return "essentia"
    if backend == "essentia":
        raise AnalysisError(
            "key backend 'essentia' requested but essentia is not importable; "
            "install the extra (`uv sync --extra essentia`) or use --key-backend librosa"
        )
    return "librosa"


def key_model_version(backend: KeyBackend = "auto") -> ModelVersion:
    """The model record for whichever key backend `estimate_key` will use."""
    if resolve_key_backend(backend) == "essentia":
        return ModelVersion(name="essentia-keyextractor", version=_package_version("essentia"))
    return ModelVersion(
        name="librosa-krumhansl", version=_package_version("librosa"), source="chroma_cqt"
    )


def estimate_key(audio: np.ndarray, backend: KeyBackend = "auto") -> KeyInfo:
    """Estimate the key. "auto" prefers Essentia when importable and falls back to librosa."""
    if resolve_key_backend(backend) == "essentia":
        return estimate_key_essentia(audio)
    return estimate_key_librosa(audio)


# --- Loudness ----------------------------------------------------------------------------


def true_peak(audio: np.ndarray) -> float:
    """Largest absolute sample of the 4x oversampled signal, computed in overlapping blocks.

    Each block is extended by a small overlap on both sides so the polyphase filter has context
    at block edges; only the interior of each block contributes to the maximum. Memory is bounded
    by the block size instead of the input length.
    """
    from scipy.signal import resample_poly

    block = TRUE_PEAK_BLOCK_SECONDS * SAMPLE_RATE
    overlap = TRUE_PEAK_OVERLAP_SAMPLES
    n = audio.shape[-1]
    peak = 0.0
    for start in range(0, n, block):
        lo = max(0, start - overlap)
        hi = min(n, start + block + overlap)
        up = resample_poly(audio[:, lo:hi], TRUE_PEAK_OVERSAMPLING, 1, axis=1)
        first = (start - lo) * TRUE_PEAK_OVERSAMPLING
        last = first + min(block, n - start) * TRUE_PEAK_OVERSAMPLING
        peak = max(peak, float(np.max(np.abs(up[:, first:last]))))
    return peak


def measure_loudness(audio: np.ndarray) -> Loudness:
    """Integrated LUFS (BS.1770) and true peak in dBTP from a 4x oversampled signal."""
    pyln = require("pyloudnorm")

    meter = pyln.Meter(SAMPLE_RATE)
    lufs = float(meter.integrated_loudness(audio.T.astype(np.float64)))
    peak = true_peak(audio)
    dbtp = 20.0 * np.log10(peak) if peak > 0 else SILENCE_DBTP
    if not np.isfinite(lufs):
        lufs = SILENCE_LUFS
    return Loudness(integrated_lufs=round(lufs, 2), true_peak_dbtp=round(float(dbtp), 2))


# --- Orchestrator ------------------------------------------------------------------------


def analyze(audio: np.ndarray, source: str, *, options: AnalyzeOptions | None = None) -> Analysis:
    """Analyze decoded audio of shape (2, n_samples) at 44.1 kHz."""
    options = options or AnalyzeOptions()
    key_backend = resolve_key_backend(options.key_backend)
    # Fail fast, before the slow beat model runs: a missing extra must not surface only after it.
    if key_backend == "librosa":
        require("librosa")
    require("pyloudnorm")
    beats, downbeats = detect_beats(
        audio, checkpoint=options.beat_checkpoint, device=options.device
    )
    grid = build_grid(beats, downbeats)
    key = estimate_key(audio, options.key_backend)
    loudness = measure_loudness(audio)
    return Analysis(
        source=source,
        duration=round(audio.shape[-1] / SAMPLE_RATE, 3),
        sample_rate=SAMPLE_RATE,
        grid=grid,
        key=key,
        loudness=loudness,
        models={
            "beats": ModelVersion(
                name="beat_this",
                version=_package_version("beat_this"),
                source=f"{options.beat_checkpoint} checkpoint",
            ),
            "grid_postprocess": ModelVersion(
                name="grid-postprocess",
                version=GRID_POSTPROCESS_VERSION,
                source="outlier beat cleanup + backward lead-in extrapolation",
            ),
            "key": key_model_version(options.key_backend),
            "loudness": ModelVersion(name="pyloudnorm", version=_package_version("pyloudnorm")),
        },
    )
