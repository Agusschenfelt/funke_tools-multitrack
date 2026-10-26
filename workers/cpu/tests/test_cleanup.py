import os
from pathlib import Path

import pytest

from worker_cpu import cleanup
from worker_cpu.storage import LocalStorage

NOW = 1_800_000_000.0
HOUR = 3600.0


def age(storage: LocalStorage, song_id: str, name: str, hours: float) -> None:
    path = storage.root / song_id / name
    stamp = NOW - hours * HOUR
    os.utime(path, (stamp, stamp))


def test_deletes_only_songs_older_than_24_hours(storage_root: Path) -> None:
    storage = LocalStorage(storage_root)
    for song_id in ("old", "fresh", "edge"):
        storage.put_bytes(song_id, "source.wav", b"x")
    age(storage, "old", "source.wav", 25)
    age(storage, "fresh", "source.wav", 1)
    age(storage, "edge", "source.wav", 24)

    deleted = cleanup.cleanup_job(now=NOW)

    assert deleted == ["old"]
    assert [e.song_id for e in storage.list_songs()] == ["edge", "fresh"]


def test_later_artifacts_do_not_extend_a_songs_life(storage_root: Path) -> None:
    storage = LocalStorage(storage_root)
    storage.put_bytes("s1", "source.wav", b"x")
    storage.put_bytes("s1", "stems/drums.wav", b"x")
    age(storage, "s1", "source.wav", 30)
    age(storage, "s1", "stems/drums.wav", 2)

    assert cleanup.cleanup_job(now=NOW) == ["s1"]
    assert storage.list_songs() == []


def test_empty_or_missing_root_is_a_no_op(storage_root: Path) -> None:
    assert cleanup.cleanup_job(now=NOW) == []


def test_main_prints_deleted_ids(
    storage_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    storage = LocalStorage(storage_root)
    storage.put_bytes("s1", "source.wav", b"x")
    age(storage, "s1", "source.wav", 48)
    monkeypatch.setattr(cleanup.time, "time", lambda: NOW)
    cleanup.main()
    out = capsys.readouterr().out
    assert "deleted 1 expired song(s)" in out
    assert "s1" in out
