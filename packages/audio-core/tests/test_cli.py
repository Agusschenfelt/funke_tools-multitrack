from pathlib import Path

from typer.testing import CliRunner

from audio_core.cli import app

runner = CliRunner()


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "analyze" in result.output
    assert "separate" in result.output


def test_analyze_not_implemented(sine_wav: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["analyze", str(sine_wav), "--out", str(tmp_path / "out")])
    assert result.exit_code == 2
    assert "not implemented" in result.output


def test_separate_not_implemented(sine_wav: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["separate", str(sine_wav), "--out", str(tmp_path / "out")])
    assert result.exit_code == 2
    assert "not implemented" in result.output
