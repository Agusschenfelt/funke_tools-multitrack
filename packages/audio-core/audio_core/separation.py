"""Stem separation."""

from pathlib import Path

import numpy as np

from audio_core.models import StemSet


def separate(
    audio: np.ndarray,
    source: str,
    model: str = "htdemucs_6s",
    out_dir: Path = Path("out"),
) -> StemSet:
    """Separate decoded audio of shape (2, n_samples) into stems written to out_dir."""
    raise NotImplementedError("implemented in T4")
