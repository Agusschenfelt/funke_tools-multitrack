"""CLI tests for ``sections`` and ``analyze --sections`` on the synthetic structured song."""

import json
import zipfile
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pytest
import soundfile as sf
from typer.testing import CliRunner

from audio_core.cli import app
from audio_core.constants import SAMPLE_RATE
from audio_core.models import Analysis, Grid, ModelVersion, Sections, Stem, StemSet
from tests.conftest import requires_ffmpeg
from tests.test_guide import build_library
from tests.test_sections import make_song

runner = CliRunner()


class Song(NamedTuple):
    root: Path
    wav: Path
    grid: Grid
    audio: np.ndarray
    analysis_path: Path
    stems_dir: Path


def _write_stemset(directory: Path, stems: dict[str, np.ndarray]) -> None:
    directory.mkdir()
    entries = []
    for name, mono in stems.items():
        sf.write(str(directory / f"{name}.wav"), np.stack([mono, mono], axis=1), SAMPLE_RATE)
        entries.append(Stem(name=name, path=f"{name}.wav", samples=mono.size))
    stemset = StemSet(
        source="song.wav",
        model=ModelVersion(name="htdemucs_6s", version="4.0"),
        device="cpu",
        elapsed_seconds=1,
        load_seconds=1,
        audio_seconds=next(iter(stems.values())).size / SAMPLE_RATE,
        samples=next(iter(stems.values())).size,
        stems=entries,
    )
    (directory / "stemset.json").write_text(stemset.model_dump_json(), encoding="utf-8")


@pytest.fixture(scope="module")
def song(tmp_path_factory: pytest.TempPathFactory) -> Song:
    root = tmp_path_factory.mktemp("sections_cli")
    audio, vocals, grid = make_song()
    wav = root / "song.wav"
    sf.write(str(wav), np.stack([audio, audio], axis=1), SAMPLE_RATE)
    analysis = Analysis(
        source=str(wav),
        duration=audio.size / SAMPLE_RATE,
        sample_rate=SAMPLE_RATE,
        grid=grid,
        key=None,
        loudness=None,
        models={"beats": ModelVersion(name="beat_this", version="1")},
    )
    analysis_path = root / "analysis.json"
    analysis_path.write_text(analysis.model_dump_json(), encoding="utf-8")
    backing = (0.05 * audio).astype(np.float32)
    _write_stemset(root / "stems", {"drums": backing, "vocals": vocals})
    return Song(root, wav, grid, audio, analysis_path, root / "stems")


@pytest.fixture
def decoded(song: Song, monkeypatch: pytest.MonkeyPatch) -> None:
    """Serve the song from memory so most tests need no ffmpeg."""
    stereo = np.stack([song.audio, song.audio])
    monkeypatch.setattr("audio_core.cli.decode", lambda path: stereo)


def _read_sections(out: Path) -> Sections:
    return Sections.model_validate_json((out / "sections.json").read_text(encoding="utf-8"))


def _assert_on_downbeats(detected: Sections, grid: Grid) -> None:
    downbeats = np.asarray(grid.downbeats)
    for section in detected.sections:
        assert np.abs(downbeats - section.start).min() < 1e-3, section


def test_sections_command_writes_valid_sections_on_downbeats(
    song: Song, decoded: None, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    result = runner.invoke(
        app, ["sections", str(song.wav), "--analysis", str(song.analysis_path), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    detected = _read_sections(out)
    assert detected.source == str(song.wav)
    assert len(detected.sections) >= 5
    assert detected.sections[0].start == 0.0
    assert all(s.confidence is not None for s in detected.sections)
    _assert_on_downbeats(detected, song.grid)
    assert "chorus" in result.output
    assert "bar 1 " in result.output
    assert "conf " in result.output


def test_sections_command_uses_the_vocals_stem(song: Song, decoded: None, tmp_path: Path) -> None:
    blind, informed = tmp_path / "blind", tmp_path / "informed"
    base = ["sections", str(song.wav), "--analysis", str(song.analysis_path)]
    assert runner.invoke(app, [*base, "--out", str(blind)]).exit_code == 0
    result = runner.invoke(app, [*base, "--stems", str(song.stems_dir), "--out", str(informed)])
    assert result.exit_code == 0, result.output
    without, with_vocals = _read_sections(blind), _read_sections(informed)
    assert [s.start for s in with_vocals.sections] == [s.start for s in without.sections]
    # Known vocals raise the confidence of the vocal-dependent labels (verse, chorus).
    assert sum(s.confidence for s in with_vocals.sections) > sum(  # type: ignore[misc]
        s.confidence for s in without.sections
    )


def test_sections_command_without_a_vocals_stem_exits_1(
    song: Song, decoded: None, tmp_path: Path
) -> None:
    stems = tmp_path / "stems"
    _write_stemset(stems, {"drums": (0.05 * song.audio).astype(np.float32)})
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "sections",
            str(song.wav),
            "--analysis",
            str(song.analysis_path),
            "--stems",
            str(stems),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 1
    assert "vocals" in result.output
    assert not (out / "sections.json").exists()


def test_sections_command_without_a_grid_exits_1(song: Song, decoded: None, tmp_path: Path) -> None:
    analysis = Analysis.model_validate_json(song.analysis_path.read_text(encoding="utf-8"))
    bare = tmp_path / "analysis.json"
    bare.write_text(analysis.model_copy(update={"grid": None}).model_dump_json(), encoding="utf-8")
    out = tmp_path / "out"
    result = runner.invoke(
        app, ["sections", str(song.wav), "--analysis", str(bare), "--out", str(out)]
    )
    assert result.exit_code == 1
    assert "grid" in result.output
    assert not out.exists()


def test_sections_command_missing_analysis_exits_1(song: Song, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["sections", str(song.wav), "--analysis", str(tmp_path / "nope.json"), "--out", "o"],
    )
    assert result.exit_code == 1
    assert "analysis" in result.output


@requires_ffmpeg
def test_sections_command_decodes_a_real_file(song: Song, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(
        app, ["sections", str(song.wav), "--analysis", str(song.analysis_path), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    _assert_on_downbeats(_read_sections(out), song.grid)


@requires_ffmpeg
def test_analyze_sections_writes_both_files_and_records_the_model(
    song: Song, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beats = np.asarray(song.grid.beats)
    monkeypatch.setattr("audio_core.analysis.detect_beats", lambda audio, **_: (beats, beats[::4]))
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        ["analyze", str(song.wav), "--out", str(out), "--key-backend", "librosa", "--sections"],
    )
    assert result.exit_code == 0, result.output
    analysis = Analysis.model_validate_json((out / "analysis.json").read_text(encoding="utf-8"))
    detected = _read_sections(out)
    assert analysis.models["sections"].name == "librosa-laplacian+heuristics"
    assert detected.source == str(song.wav)
    _assert_on_downbeats(detected, song.grid)
    assert "BPM 120" in result.output
    assert "chorus" in result.output


@requires_ffmpeg
def test_analyze_defaults_to_no_sections(
    song: Song, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beats = np.asarray(song.grid.beats)
    monkeypatch.setattr("audio_core.analysis.detect_beats", lambda audio, **_: (beats, beats[::4]))
    out = tmp_path / "out"
    result = runner.invoke(
        app, ["analyze", str(song.wav), "--out", str(out), "--key-backend", "librosa"]
    )
    assert result.exit_code == 0, result.output
    analysis = Analysis.model_validate_json((out / "analysis.json").read_text(encoding="utf-8"))
    assert "sections" not in analysis.models
    assert not (out / "sections.json").exists()


def test_detected_sections_feed_the_stage_pack(song: Song, decoded: None, tmp_path: Path) -> None:
    detect_out = tmp_path / "detected"
    detected_run = runner.invoke(
        app,
        [
            "sections",
            str(song.wav),
            "--analysis",
            str(song.analysis_path),
            "--stems",
            str(song.stems_dir),
            "--out",
            str(detect_out),
        ],
    )
    assert detected_run.exit_code == 0, detected_run.output
    detected = _read_sections(detect_out)

    cues = build_library(tmp_path / "cues" / "es")
    pack_out = tmp_path / "pack"
    pack = runner.invoke(
        app,
        [
            "stagepack",
            str(song.stems_dir),
            "--analysis",
            str(song.analysis_path),
            "--sections",
            str(detect_out / "sections.json"),
            "--cues-dir",
            str(cues),
            "--destination",
            "daw",
            "--out",
            str(pack_out),
        ],
    )
    assert pack.exit_code == 0, pack.output
    (archive_path,) = pack_out.glob("*.zip")
    with zipfile.ZipFile(archive_path) as archive:
        report = json.loads(archive.read("stagepack.json"))
        listing = archive.read("Secciones.txt").decode("utf-8")
    # Every detected section got a cue: nothing missing or skipped, only the count-in tie-break
    # (a section starting where the count-in ends) may drop a cue.
    warnings = report["guide_warnings"]
    assert not [w for w in warnings if "skipped" in w], warnings
    assert len([w for w in warnings if "dropped" in w]) <= 1, warnings
    assert len(listing.strip().splitlines()) == len(detected.sections)
