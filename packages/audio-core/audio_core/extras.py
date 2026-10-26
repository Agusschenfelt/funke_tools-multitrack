"""Optional dependency groups of audio-core and the error raised when one is missing.

The light core (models, io, timeline, click, guide, stagepack) needs none of them. Analysis and
separation import their heavy libraries lazily through ``require`` so a missing extra produces a
clear message naming the extra to install instead of a bare ``ModuleNotFoundError``.
"""

import importlib
from types import ModuleType

# Which extra provides each heavy top-level module.
EXTRA_FOR_MODULE = {
    "torch": "ml",
    "torchaudio": "ml",
    "demucs": "ml",
    "beat_this": "ml",
    "librosa": "analysis",
    "pyloudnorm": "analysis",
    "numba": "analysis",
}


class MissingExtraError(RuntimeError):
    """Raised when a pipeline step needs an optional extra that is not installed."""

    def __init__(self, module: str, extra: str) -> None:
        super().__init__(
            f"{module} is not installed; install the optional extra "
            f"'audio-core[{extra}]' (uv sync --extra {extra})"
        )
        self.module = module
        self.extra = extra


def require(module: str) -> ModuleType:
    """Import ``module`` (a dotted name), raising ``MissingExtraError`` when its extra is absent."""
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as exc:
        top = module.split(".")[0]
        if exc.name is not None and exc.name.split(".")[0] in EXTRA_FOR_MODULE:
            missing = exc.name.split(".")[0]
            raise MissingExtraError(missing, EXTRA_FOR_MODULE[missing]) from exc
        if top in EXTRA_FOR_MODULE and exc.name == top:
            raise MissingExtraError(top, EXTRA_FOR_MODULE[top]) from exc
        raise
