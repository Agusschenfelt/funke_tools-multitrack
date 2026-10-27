"""Local song storage used by the API.

IMPORTANT: this deliberately duplicates the on-disk layout and the safe-name rules of
``worker_cpu.storage.LocalStorage`` (``<root>/<song_id>/<name>``) because the API must not depend
on the worker package (it pulls torch). Both implementations must stay in sync. Follow-up: extract
the ``Storage`` protocol and ``LocalStorage`` into a shared light package (or into audio-core's
light core) and delete this copy.

Well-known names (same as the worker): ``source.<ext>``, ``analysis.json``, ``sections.json``,
``stems/<stem>.wav`` + ``stems/stemset.json``, ``packs/<name>.zip``.
"""

import re
import shutil
from pathlib import Path

SOURCE_PREFIX = "source"
ANALYSIS = "analysis.json"
SECTIONS = "sections.json"
STEMSET = "stems/stemset.json"
STEMS_PREFIX = "stems/"
PACKS_PREFIX = "packs/"
JOBS_PREFIX = "jobs/"
INCOMING_DIR = ".incoming"  # not a valid song id, so the worker's list_songs ignores it

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SAFE_PART = re.compile(r"^[^/\\\x00]+$")


def job_result_name(job_id: str) -> str:
    """Where the worker records what a finished job returned (``worker_cpu.jobs.tracked``)."""
    return f"{JOBS_PREFIX}{job_id}.json"


class StorageError(RuntimeError):
    """Raised for invalid ids or names and for missing artifacts."""


def check_song_id(song_id: str) -> str:
    if not _SAFE_ID.match(song_id):
        raise StorageError(f"invalid song id: {song_id!r}")
    return song_id


def check_name(name: str) -> str:
    parts = name.split("/")
    if not name or any(p in ("", ".", "..") or not _SAFE_PART.match(p) for p in parts):
        raise StorageError(f"invalid artifact name: {name!r}")
    return name


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _song_dir(self, song_id: str) -> Path:
        return self.root / check_song_id(song_id)

    def path(self, song_id: str, name: str) -> Path:
        return self._song_dir(song_id) / check_name(name)

    def incoming_dir(self) -> Path:
        directory = self.root / INCOMING_DIR
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def put_file(self, song_id: str, name: str, source: Path) -> None:
        target = self.path(song_id, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    def put_bytes(self, song_id: str, name: str, data: bytes) -> None:
        target = self.path(song_id, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def get_bytes(self, song_id: str, name: str) -> bytes:
        path = self.path(song_id, name)
        if not path.is_file():
            raise StorageError(f"{name} not found for song {song_id}")
        return path.read_bytes()

    def exists(self, song_id: str, name: str) -> bool:
        return self.path(song_id, name).is_file()

    def list_names(self, song_id: str, prefix: str = "") -> list[str]:
        directory = self._song_dir(song_id)
        if not directory.is_dir():
            return []
        names = (p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file())
        return sorted(n for n in names if n.startswith(prefix))

    def delete_song(self, song_id: str) -> None:
        shutil.rmtree(self._song_dir(song_id), ignore_errors=True)
