"""Song storage behind a small interface.

Every artifact belongs to a song id and is addressed by a relative *name* such as
``analysis.json`` or ``stems/drums.wav``. Jobs never see filesystem layout: they move bytes and
files in and out through this protocol and do their audio work in a private temporary directory.
That keeps a future object-store implementation (R2 is S3 compatible, a name maps to the key
``<song_id>/<name>``) a drop-in replacement for ``LocalStorage``.

Well-known names:

* ``source.<ext>``: the uploaded audio (``SOURCE_PREFIX``).
* ``analysis.json``: analysis output.
* ``sections.json``: the sections the user sees and edits; ``sections.detected.json``: the latest
  detector output (see ``analyze_job`` for who writes which).
* ``stems/<stem>.wav`` plus ``stems/stemset.json``: separation output (``STEMS_PREFIX``).
* ``packs/<name>.zip``: built Stage Packs (``PACKS_PREFIX``).
"""

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

SOURCE_PREFIX = "source"
ANALYSIS = "analysis.json"
SECTIONS = "sections.json"
SECTIONS_DETECTED = "sections.detected.json"
STEMSET = "stems/stemset.json"
STEMS_PREFIX = "stems/"
PACKS_PREFIX = "packs/"

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SAFE_PART = re.compile(r"^[^/\\\x00]+$")


class StorageError(RuntimeError):
    """Raised for invalid ids or names and for missing artifacts."""


@dataclass(frozen=True)
class SongEntry:
    song_id: str
    modified: float  # POSIX seconds of the newest artifact
    created: float  # POSIX seconds of the oldest artifact (the upload); the expiry job uses this


@runtime_checkable
class Storage(Protocol):
    def put_file(self, song_id: str, name: str, source: Path) -> None: ...

    def put_bytes(self, song_id: str, name: str, data: bytes) -> None: ...

    def get_file(self, song_id: str, name: str, destination: Path) -> None: ...

    def get_bytes(self, song_id: str, name: str) -> bytes: ...

    def exists(self, song_id: str, name: str) -> bool: ...

    def list_names(self, song_id: str, prefix: str = "") -> list[str]:
        """Names of a song's artifacts starting with ``prefix``, sorted."""
        ...

    def delete_song(self, song_id: str) -> None: ...

    def list_songs(self) -> list[SongEntry]: ...


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
    """Songs on local disk: ``<root>/<song_id>/<name>``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _song_dir(self, song_id: str) -> Path:
        return self.root / check_song_id(song_id)

    def _path(self, song_id: str, name: str) -> Path:
        return self._song_dir(song_id) / check_name(name)

    def put_file(self, song_id: str, name: str, source: Path) -> None:
        target = self._path(song_id, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    def put_bytes(self, song_id: str, name: str, data: bytes) -> None:
        target = self._path(song_id, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def get_file(self, song_id: str, name: str, destination: Path) -> None:
        source = self._existing(song_id, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    def get_bytes(self, song_id: str, name: str) -> bytes:
        return self._existing(song_id, name).read_bytes()

    def exists(self, song_id: str, name: str) -> bool:
        return self._path(song_id, name).is_file()

    def list_names(self, song_id: str, prefix: str = "") -> list[str]:
        directory = self._song_dir(song_id)
        if not directory.is_dir():
            return []
        names = (p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file())
        return sorted(n for n in names if n.startswith(prefix))

    def delete_song(self, song_id: str) -> None:
        shutil.rmtree(self._song_dir(song_id), ignore_errors=True)

    def list_songs(self) -> list[SongEntry]:
        if not self.root.is_dir():
            return []
        entries = []
        for directory in sorted(self.root.iterdir()):
            if not directory.is_dir() or not _SAFE_ID.match(directory.name):
                continue
            times = [p.stat().st_mtime for p in directory.rglob("*") if p.is_file()]
            fallback = directory.stat().st_mtime
            entries.append(
                SongEntry(
                    directory.name,
                    modified=max(times) if times else fallback,
                    created=min(times) if times else fallback,
                )
            )
        return entries

    def _existing(self, song_id: str, name: str) -> Path:
        path = self._path(song_id, name)
        if not path.is_file():
            raise StorageError(f"{name} not found for song {song_id}")
        return path
