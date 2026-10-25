"""Stem separation with Demucs (Meta, MIT).

Only the checkpoints listed in ``ALLOWED_MODELS`` (and in ``MODELS.md``) may be used. Weights are
not vendored: Demucs downloads them on first use from the Meta release URLs into the torch hub
cache. Heavy imports (torch, demucs) stay inside ``separate`` so the CLI ``--help`` stays fast.
"""

import os
import time
from importlib import metadata
from pathlib import Path

import numpy as np

from audio_core.constants import CHANNELS, DTYPE, SAMPLE_RATE
from audio_core.io import write_wav
from audio_core.models import ModelVersion, Stem, StemSet

DEMUCS_SOURCE = "https://github.com/facebookresearch/demucs"
DEFAULT_MODEL = "htdemucs_6s"
DEVICES = ("cpu", "cuda", "mps")
OVERLAP = 0.25
# Demucs divides by the mixture standard deviation; this keeps silent input finite.
_NORMALIZE_EPSILON = 1e-8

# Keep in sync with MODELS.md (a unit test enforces that every key appears there).
ALLOWED_MODELS: dict[str, tuple[str, ...]] = {
    "htdemucs_ft": ("drums", "bass", "other", "vocals"),
    "htdemucs_6s": ("drums", "bass", "other", "vocals", "guitar", "piano"),
}


class SeparationError(RuntimeError):
    """Raised when stem separation cannot run or produces an unexpected result."""


def _fit_length(stem: np.ndarray, samples: int) -> np.ndarray:
    """Trim or zero-pad a (channels, n) array to exactly ``samples`` samples.

    Demucs pads internally to whole segments and trims back, so the length normally matches; this
    guards the contract (stems have exactly the input sample count) against off-by-a-few results.
    """
    n = stem.shape[-1]
    if n == samples:
        return stem
    if n > samples:
        return stem[..., :samples]
    return np.pad(stem, ((0, 0), (0, samples - n)))


def separate(
    audio: np.ndarray,
    source: str,
    model: str = DEFAULT_MODEL,
    out_dir: Path = Path("out"),
    *,
    device: str = "cpu",
    shifts: int = 1,
) -> StemSet:
    """Separate decoded audio of shape (2, n_samples) at 44.1 kHz into stems written to out_dir.

    Writes one float32 44.1 kHz WAV per stem (``<stem>.wav``, exactly the input sample count).
    ``elapsed_seconds`` is the wall clock of ``apply_model`` only; ``load_seconds`` covers model
    loading (including any first-use weight download). The caller writes ``stemset.json``.
    """
    if model not in ALLOWED_MODELS:
        raise SeparationError(
            f"model {model!r} is not allowed; choose one of {sorted(ALLOWED_MODELS)}"
        )
    if device not in DEVICES:
        raise SeparationError(f"unknown device {device!r}; choose one of {list(DEVICES)}")
    # shifts=0 is the only deterministic setting: Demucs draws random shifts when shifts > 0.
    if shifts < 0:
        raise SeparationError("shifts must be 0 or greater")
    if audio.ndim != 2 or audio.shape[0] != CHANNELS or audio.shape[1] == 0:
        raise SeparationError(f"expected non-empty audio shaped (2, n_samples), got {audio.shape}")

    try:
        import torch
        from demucs.apply import apply_model
        from demucs.pretrained import get_model

        torch.set_num_threads(os.cpu_count() or 1)

        load_start = time.perf_counter()
        bag = get_model(model)
        bag.eval()
        load_seconds = time.perf_counter() - load_start

        if list(bag.sources) != list(ALLOWED_MODELS[model]):
            raise SeparationError(
                f"model {model!r} reports stems {list(bag.sources)}, "
                f"expected {list(ALLOWED_MODELS[model])}"
            )
        if bag.samplerate != SAMPLE_RATE:
            raise SeparationError(f"model sample rate {bag.samplerate} != {SAMPLE_RATE}")

        samples = audio.shape[-1]
        mix = torch.from_numpy(np.ascontiguousarray(audio, dtype=DTYPE))
        reference = mix.mean(dim=0)
        mean, std = reference.mean(), reference.std()
        normalized = (mix - mean) / (std + _NORMALIZE_EPSILON)

        apply_start = time.perf_counter()
        with torch.no_grad():
            estimates = apply_model(
                bag,
                normalized[None],
                shifts=shifts,
                split=True,
                overlap=OVERLAP,
                device=device,
            )[0]
        elapsed = time.perf_counter() - apply_start
        estimates = (estimates * (std + _NORMALIZE_EPSILON) + mean).cpu().numpy()
    except SeparationError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface any model/download/inference failure
        raise SeparationError(f"separation failed: {exc}") from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    stems: list[Stem] = []
    for name, data in zip(ALLOWED_MODELS[model], estimates, strict=True):
        fitted = _fit_length(np.ascontiguousarray(data, dtype=DTYPE), samples)
        assert fitted.shape == (CHANNELS, samples)
        write_wav(out_dir / f"{name}.wav", fitted)
        stems.append(Stem(name=name, path=f"{name}.wav", samples=samples))

    try:
        version = metadata.version("demucs")
    except metadata.PackageNotFoundError:
        version = "unknown"
    return StemSet(
        source=source,
        model=ModelVersion(name=model, version=version, source=DEMUCS_SOURCE),
        device=device,
        shifts=shifts,
        elapsed_seconds=round(elapsed, 3),
        load_seconds=round(load_seconds, 3),
        audio_seconds=round(samples / SAMPLE_RATE, 3),
        samples=samples,
        stems=stems,
    )
