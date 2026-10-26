"""The light core must import and run without the heavy extras (torch, demucs, beat_this)."""

import subprocess
import sys
import textwrap

import pytest

from audio_core.extras import MissingExtraError, require

BLOCKER = textwrap.dedent(
    """
    import importlib.abc
    import sys

    BLOCKED = {"torch", "torchaudio", "demucs", "beat_this", "librosa", "pyloudnorm", "numba"}

    class Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name.split(".")[0] in BLOCKED:
                raise ModuleNotFoundError(f"blocked for test: {name}", name=name)
            return None

    sys.meta_path.insert(0, Blocker())
    """
)


def run_blocked(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", BLOCKER + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_light_modules_import_without_heavy_extras() -> None:
    result = run_blocked(
        """
        import audio_core.models, audio_core.stagepack, audio_core.io
        import audio_core.timeline, audio_core.click, audio_core.guide, audio_core.cli
        heavy = {"torch", "demucs", "beat_this", "librosa", "numba"}
        loaded = heavy & {m.split(".")[0] for m in sys.modules}
        assert not loaded, loaded
        print("ok")
        """
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_blocker_really_blocks_torch() -> None:
    result = run_blocked("import torch")
    assert result.returncode != 0
    assert "blocked for test" in result.stderr


def test_cli_help_without_heavy_extras() -> None:
    result = run_blocked(
        """
        from typer.testing import CliRunner
        from audio_core.cli import app
        out = CliRunner().invoke(app, ["--help"])
        assert out.exit_code == 0, out.output
        """
    )
    assert result.returncode == 0, result.stderr


def test_separate_without_ml_extra_names_the_extra() -> None:
    result = run_blocked(
        """
        import numpy as np
        from audio_core.extras import MissingExtraError
        from audio_core.separation import separate
        try:
            separate(np.zeros((2, 100), dtype=np.float32), "x.wav")
        except MissingExtraError as exc:
            assert "audio-core[ml]" in str(exc), exc
            print("ok")
        """
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_cli_missing_extra_exits_1(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import audio_core.cli as cli

    def boom(*args, **kwargs):
        raise MissingExtraError("torch", "ml")

    monkeypatch.setattr(cli, "run_separate", boom)
    monkeypatch.setattr(cli, "decode", lambda path: object())
    from typer.testing import CliRunner

    result = CliRunner().invoke(cli.app, ["separate", "x.wav", "--out", str(tmp_path / "o")])
    assert result.exit_code == 1
    assert "audio-core[ml]" in result.output


def test_require_reraises_unrelated_import_errors() -> None:
    with pytest.raises(ModuleNotFoundError):
        require("definitely_not_a_module_xyz")
