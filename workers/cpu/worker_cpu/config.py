"""Environment configuration shared by the worker entry point and the jobs."""

import os
from pathlib import Path

from worker_cpu.storage import LocalStorage, Storage

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_STORAGE_ROOT = "./storage"
QUEUE_NAME = "cpu"


def redis_url() -> str:
    return os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)


def get_storage() -> Storage:
    """Storage for the current process, from ``STORAGE_ROOT`` (local disk)."""
    return LocalStorage(Path(os.environ.get("STORAGE_ROOT", DEFAULT_STORAGE_ROOT)))


def cues_dir() -> Path | None:
    """Optional override of the cue sample library (``CUES_DIR``); None uses the repo library."""
    value = os.environ.get("CUES_DIR")
    return Path(value) if value else None
