import shutil
from pathlib import Path

import fakeredis
import numpy as np
import pytest
import soundfile as sf
from audio_core.constants import SAMPLE_RATE
from audio_core.io import write_wav
from audio_core.models import Analysis, Grid, KeyInfo, ModelVersion, Stem, StemSet
from rq import Queue

from worker_cpu import jobs
from worker_cpu.storage import LocalStorage

BPM = 120.0
BARS = 16
SONG_ID = "song-1"
STEM_NAMES = ("drums", "bass", "other", "vocals", "guitar", "piano")

requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


def synthetic_grid() -> Grid:
    beats = [i * 60.0 / BPM for i in range(BARS * 4)]
    return Grid(bpm=BPM, beats=beats, downbeats=beats[::4], time_signature="4/4")


def write_song(path: Path) -> None:
    """Sixteen bars at 120 BPM: a quiet low chord, then a louder bright one with clicks."""
    n = int(BARS * 4 * 60.0 / BPM * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    half = n // 2
    low = 0.2 * (np.sin(2 * np.pi * 110 * t) + np.sin(2 * np.pi * 164.8 * t))
    high = 0.4 * (np.sin(2 * np.pi * 440 * t) + np.sin(2 * np.pi * 659.3 * t))
    mono = np.where(np.arange(n) < half, low, high)
    for beat in synthetic_grid().beats[len(synthetic_grid().beats) // 2 :]:
        start = int(beat * SAMPLE_RATE)
        mono[start : start + 400] += 0.3
    sf.write(str(path), np.stack([mono, mono], axis=1).astype(np.float32), SAMPLE_RATE)


@pytest.fixture
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "storage"
    monkeypatch.setenv("STORAGE_ROOT", str(root))
    return root


@pytest.fixture
def storage(storage_root: Path) -> LocalStorage:
    return LocalStorage(storage_root)


@pytest.fixture
def song(storage: LocalStorage, tmp_path: Path) -> str:
    wav = tmp_path / "upload.wav"
    write_song(wav)
    storage.put_file(SONG_ID, "source.wav", wav)
    return SONG_ID


@pytest.fixture
def fake_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the two model-backed calls (beat tracking and Demucs) with fast stand-ins."""

    def fake_analyze(audio: np.ndarray, source: str, *, options=None) -> Analysis:
        return Analysis(
            source=source,
            duration=round(audio.shape[-1] / SAMPLE_RATE, 3),
            sample_rate=SAMPLE_RATE,
            grid=synthetic_grid(),
            key=KeyInfo(key="A", mode="minor", camelot="8A", compatible=[]),
            loudness=None,
            models={"beats": ModelVersion(name="beat_this", version="test")},
        )

    def fake_separate(audio, source, model="htdemucs_6s", out_dir=Path("out"), **kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        stems = []
        for i, name in enumerate(STEM_NAMES):
            write_wav(out_dir / f"{name}.wav", audio * (0.2 + 0.05 * i))
            stems.append(Stem(name=name, path=f"{name}.wav", samples=audio.shape[-1]))
        return StemSet(
            source=source,
            model=ModelVersion(name=model, version="test"),
            device="cpu",
            elapsed_seconds=0.1,
            load_seconds=0.1,
            audio_seconds=audio.shape[-1] / SAMPLE_RATE,
            samples=audio.shape[-1],
            stems=stems,
        )

    monkeypatch.setattr(jobs, "run_analyze", fake_analyze)
    monkeypatch.setattr(jobs, "run_separate", fake_separate)


class StageRecorder:
    """Stand-in for the RQ job context that records every stage written to ``meta``."""

    def __init__(self) -> None:
        self.meta: dict = {}
        self.stages: list[str] = []

    def save_meta(self) -> None:
        self.stages.append(self.meta["stage"])


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> StageRecorder:
    rec = StageRecorder()
    monkeypatch.setattr(jobs, "get_current_job", lambda: rec)
    return rec


@pytest.fixture
def queue() -> Queue:
    connection = fakeredis.FakeRedis()
    return Queue("cpu", connection=connection, is_async=False)
