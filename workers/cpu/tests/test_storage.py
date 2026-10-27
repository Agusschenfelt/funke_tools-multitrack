from pathlib import Path

import pytest

from worker_cpu.storage import LocalStorage, Storage, StorageError


def test_local_storage_satisfies_the_protocol(storage: LocalStorage) -> None:
    assert isinstance(storage, Storage)


def test_bytes_and_file_round_trip(storage: LocalStorage, tmp_path: Path) -> None:
    storage.put_bytes("a1", "analysis.json", b"{}")
    assert storage.exists("a1", "analysis.json")
    assert storage.get_bytes("a1", "analysis.json") == b"{}"
    source = tmp_path / "x.wav"
    source.write_bytes(b"abc")
    storage.put_file("a1", "stems/drums.wav", source)
    out = tmp_path / "copy" / "drums.wav"
    storage.get_file("a1", "stems/drums.wav", out)
    assert out.read_bytes() == b"abc"


def test_list_names_filters_by_prefix(storage: LocalStorage) -> None:
    for name in ("source.mp3", "analysis.json", "stems/b.wav", "stems/a.wav"):
        storage.put_bytes("a1", name, b"x")
    assert storage.list_names("a1", "stems/") == ["stems/a.wav", "stems/b.wav"]
    assert storage.list_names("a1", "source") == ["source.mp3"]
    assert storage.list_names("missing") == []


def test_list_songs_reports_newest_mtime_and_delete(storage: LocalStorage) -> None:
    assert storage.list_songs() == []
    storage.put_bytes("a1", "analysis.json", b"x")
    storage.put_bytes("b2", "analysis.json", b"x")
    assert [e.song_id for e in storage.list_songs()] == ["a1", "b2"]
    assert all(e.modified > 0 for e in storage.list_songs())
    storage.delete_song("a1")
    assert [e.song_id for e in storage.list_songs()] == ["b2"]
    storage.delete_song("a1")  # idempotent


def test_missing_artifact_raises(storage: LocalStorage, tmp_path: Path) -> None:
    with pytest.raises(StorageError):
        storage.get_bytes("a1", "analysis.json")
    with pytest.raises(StorageError):
        storage.get_file("a1", "analysis.json", tmp_path / "x")


@pytest.mark.parametrize("song_id", ["", "..", "a/b", "../x", "a b"])
def test_invalid_song_ids_are_rejected(storage: LocalStorage, song_id: str) -> None:
    with pytest.raises(StorageError):
        storage.put_bytes(song_id, "analysis.json", b"x")


@pytest.mark.parametrize("name", ["", "../x", "/abs", "a//b", "a/./b", "a\\b"])
def test_invalid_names_are_rejected(storage: LocalStorage, name: str) -> None:
    with pytest.raises(StorageError):
        storage.put_bytes("a1", name, b"x")
