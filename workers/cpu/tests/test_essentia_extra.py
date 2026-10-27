"""The worker image must install Essentia (key and chords); the librosa key is only a fallback."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_worker_requests_the_essentia_extra() -> None:
    project = tomllib.loads((ROOT / "workers" / "cpu" / "pyproject.toml").read_text())["project"]
    audio_core = next(d for d in project["dependencies"] if d.startswith("audio-core"))
    assert "essentia" in audio_core


def test_worker_lock_pins_essentia() -> None:
    lock = (ROOT / "workers" / "cpu" / "uv.lock").read_text()
    block = lock.split('[[package]]\nname = "essentia"')[1].split("[[package]]")[0]
    assert "manylinux_2_17_x86_64" in block
