from pathlib import Path

import pytest
from typer.testing import CliRunner

from audio_core.cli import app
from audio_core.models import Analysis
from tests.conftest import ClickTrack, requires_ffmpeg

runner = CliRunner()


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "analyze" in result.output
    assert "separate" in result.output


@requires_ffmpeg
def test_analyze_undecodable_input_exits_1(tmp_path: Path) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("not audio", encoding="utf-8")
    out = tmp_path / "out"
    result = runner.invoke(app, ["analyze", str(bad), "--out", str(out)])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert not out.exists()


def test_analyze_missing_input_exits_1(tmp_path: Path) -> None:
    result = runner.invoke(app, ["analyze", str(tmp_path / "x.wav"), "--out", str(tmp_path / "o")])
    assert result.exit_code == 1
    assert "not found" in result.output


@requires_ffmpeg
def test_analyze_success_writes_parseable_json(
    click_track_wav: ClickTrack, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Beat tracking is stubbed with the known grid so the test needs no model download."""
    monkeypatch.setattr(
        "audio_core.analysis.detect_beats",
        lambda audio, **_: (click_track_wav.beat_times, click_track_wav.downbeat_times),
    )
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        ["analyze", str(click_track_wav.path), "--out", str(out), "--key-backend", "librosa"],
    )
    assert result.exit_code == 0, result.output
    analysis = Analysis.model_validate_json((out / "analysis.json").read_text(encoding="utf-8"))
    assert analysis.grid is not None
    assert analysis.grid.bpm == pytest.approx(120.0, abs=0.5)
    assert analysis.grid.time_signature == "4/4"
    assert analysis.models["key"].name == "librosa-krumhansl"
    assert "BPM 120" in result.output


def test_analyze_essentia_backend_unavailable_exits_1(
    sine_wav: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("audio_core.analysis._essentia_available", lambda: False)
    result = runner.invoke(
        app, ["analyze", str(sine_wav), "--out", str(tmp_path / "o"), "--key-backend", "essentia"]
    )
    assert result.exit_code == 1
    assert "essentia" in result.output


def test_separate_unknown_model_exits_1(sine_wav: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(app, ["separate", str(sine_wav), "--out", str(out), "--model", "nope"])
    assert result.exit_code == 1
    assert "htdemucs_6s" in result.output
    assert not (out / "stemset.json").exists()
