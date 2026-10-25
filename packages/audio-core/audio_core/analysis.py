"""Tempo grid, key and loudness analysis."""

import numpy as np

from audio_core.models import Analysis


def analyze(audio: np.ndarray, source: str) -> Analysis:
    """Analyze decoded audio of shape (2, n_samples)."""
    raise NotImplementedError("implemented in T3")
