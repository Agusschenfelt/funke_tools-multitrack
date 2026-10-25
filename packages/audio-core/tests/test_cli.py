from pathlib import Path

from typer.testing import CliRunner

from audio_core.cli import app
from tests.conftest import requires_ffmpeg

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
def test_separate_not_implemented(sine_wav: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["separate", str(sine_wav), "--out", str(tmp_path / "out")])
    assert result.exit_code == 2
    assert "not implemented" in result.output
