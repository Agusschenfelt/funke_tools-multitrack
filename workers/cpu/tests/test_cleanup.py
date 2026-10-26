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


def test_deletes_only_songs_older_than_ttl_plus_orphan_grace(storage_root: Path) -> None:
    storage = LocalStorage(storage_root)
    for song_id in ("old", "fresh", "edge"):
        storage.put_bytes(song_id, "source.wav", b"x")
    age(storage, "old", "source.wav", 31)
    age(storage, "fresh", "source.wav", 25)
    age(storage, "edge", "source.wav", 30)

    deleted = cleanup.cleanup_job(now=NOW)

    assert deleted == ["old"]
    assert [e.song_id for e in storage.list_songs()] == ["edge", "fresh"]


def test_later_artifacts_do_not_extend_a_songs_life(storage_root: Path) -> None:
    storage = LocalStorage(storage_root)
    storage.put_bytes("s1", "source.wav", b"x")
    storage.put_bytes("s1", "stems/drums.wav", b"x")
    age(storage, "s1", "source.wav", 40)
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
    assert "deleted 1 orphaned song(s)" in out
    assert "s1" in out


def test_one_failing_song_does_not_abort_the_run(storage_root: Path) -> None:
    storage = LocalStorage(storage_root)
    for song_id in ("a", "b", "c"):
        storage.put_bytes(song_id, "source.wav", b"x")
        age(storage, song_id, "source.wav", 48)
    real_delete = storage.delete_song

    def flaky(song_id: str) -> None:
        if song_id == "b":
            raise OSError("disk error")
        real_delete(song_id)

    storage.delete_song = flaky  # type: ignore[method-assign]

    assert cleanup.cleanup_job(now=NOW, storage=storage) == ["a", "c"]
    assert [e.song_id for e in storage.list_songs()] == ["b"]  # retried on the next run

    storage.delete_song = real_delete  # type: ignore[method-assign]
    assert cleanup.cleanup_job(now=NOW, storage=storage) == ["b"]


def test_song_ttl_is_env_overridable_with_a_24_hour_default(
    storage_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SONG_TTL_HOURS", raising=False)
    assert cleanup.song_ttl_seconds() == 24 * HOUR
    monkeypatch.setenv("SONG_TTL_HOURS", "2")
    assert cleanup.song_ttl_seconds() == 2 * HOUR
    for bad in ("abc", "0", "-3"):
        monkeypatch.setenv("SONG_TTL_HOURS", bad)
        assert cleanup.song_ttl_seconds() == 24 * HOUR

    monkeypatch.setenv("SONG_TTL_HOURS", "2")
    storage = LocalStorage(storage_root)
    storage.put_bytes("s1", "source.wav", b"x")
    age(storage, "s1", "source.wav", 9)
    assert cleanup.cleanup_job(now=NOW) == ["s1"]
    storage.put_bytes("s2", "source.wav", b"x")
    age(storage, "s2", "source.wav", 7)  # past the 2 h TTL but inside the 6 h orphan grace
    assert cleanup.cleanup_job(now=NOW) == []


def test_a_song_within_the_api_expiry_window_is_never_touched(storage_root: Path) -> None:
    """Between the TTL and TTL + grace the API sweep (and its in-flight deferral) owns the song."""
    storage = LocalStorage(storage_root)
    storage.put_bytes("s1", "source.wav", b"x")
    age(storage, "s1", "source.wav", 27)

    assert cleanup.cleanup_job(now=NOW) == []
    assert [e.song_id for e in storage.list_songs()] == ["s1"]


def test_a_fresh_job_lock_protects_an_old_song(storage_root: Path) -> None:
    storage = LocalStorage(storage_root)
    storage.put_bytes("busy", "source.wav", b"x")
    storage.put_bytes("busy", "jobs/job-1.lock", b"")
    storage.put_bytes("idle", "source.wav", b"x")
    for song_id in ("busy", "idle"):
        age(storage, song_id, "source.wav", 48)
    age(storage, "busy", "jobs/job-1.lock", 1)

    assert cleanup.cleanup_job(now=NOW) == ["idle"]
    assert [e.song_id for e in storage.list_songs()] == ["busy"]


def test_a_stale_job_lock_from_a_crashed_worker_does_not_protect_the_song(
    storage_root: Path,
) -> None:
    storage = LocalStorage(storage_root)
    storage.put_bytes("s1", "source.wav", b"x")
    storage.put_bytes("s1", "jobs/job-1.lock", b"")
    age(storage, "s1", "source.wav", 48)
    age(storage, "s1", "jobs/job-1.lock", 7)

    assert cleanup.cleanup_job(now=NOW) == ["s1"]


def test_result_markers_are_not_locks(storage_root: Path) -> None:
    storage = LocalStorage(storage_root)
    storage.put_bytes("s1", "source.wav", b"x")
    storage.put_bytes("s1", "jobs/job-1.json", b"{}")
    age(storage, "s1", "source.wav", 48)

    assert cleanup.cleanup_job(now=NOW) == ["s1"]
