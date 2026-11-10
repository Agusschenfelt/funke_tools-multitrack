import math
import re
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from audio_core.cli import app
from audio_core.constants import SAMPLE_RATE
from audio_core.models import ModelVersion, Stem, StemSet
from audio_core.separation import ALLOWED_MODELS, SeparationError, separate
from tests.conftest import requires_ffmpeg

MODELS_MD = Path(__file__).resolve().parents[3] / "MODELS.md"


def test_unknown_model_raises_and_lists_allowed(tmp_path: Path) -> None:
    audio = np.zeros((2, SAMPLE_RATE), dtype=np.float32)
    with pytest.raises(SeparationError) as info:
        separate(audio, "x.wav", model="htdemucs", out_dir=tmp_path)
    for name in ALLOWED_MODELS:
        assert name in str(info.value)
    assert list(tmp_path.iterdir()) == []


def test_unknown_device_raises(tmp_path: Path) -> None:
    audio = np.zeros((2, SAMPLE_RATE), dtype=np.float32)
    with pytest.raises(SeparationError, match="device"):
        separate(audio, "x.wav", out_dir=tmp_path, device="tpu")


def test_negative_shifts_rejected(tmp_path: Path) -> None:
    with pytest.raises(SeparationError, match="shifts"):
        separate(np.zeros((2, 10), dtype=np.float32), "x.wav", out_dir=tmp_path, shifts=-1)


def test_zero_shifts_is_forwarded_to_demucs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import demucs.apply
    import demucs.pretrained
    import torch

    stems = ALLOWED_MODELS["htdemucs_6s"]
    seen: dict[str, object] = {}

    class FakeBag:
        sources = list(stems)
        samplerate = SAMPLE_RATE

        def eval(self) -> None:
            pass

    def fake_apply(bag: object, mix: torch.Tensor, **kwargs: object) -> torch.Tensor:
        seen.update(kwargs)
        return torch.zeros(1, len(stems), 2, mix.shape[-1])

    monkeypatch.setattr(demucs.pretrained, "get_model", lambda name: FakeBag())
    monkeypatch.setattr(demucs.apply, "apply_model", fake_apply)
    result = separate(np.zeros((2, 100), dtype=np.float32), "x.wav", out_dir=tmp_path, shifts=0)
    assert seen["shifts"] == 0
    assert result.shifts == 0


def test_registry_matches_models_md() -> None:
    text = MODELS_MD.read_text(encoding="utf-8")
    for name, stems in ALLOWED_MODELS.items():
        row = next((line for line in text.splitlines() if f"`{name}`" in line), None)
        assert row is not None, f"{name} is missing from MODELS.md"
        assert f"{len(stems)} stems" in row
        for stem in stems:
            assert stem in row, f"stem {stem} of {name} is missing from its MODELS.md row"


def test_stemset_json_round_trip() -> None:
    original = StemSet(
        source="song.wav",
        model=ModelVersion(name="htdemucs_6s", version="4.1.0", source="https://example.test"),
        device="cpu",
        shifts=1,
        elapsed_seconds=12.5,
        load_seconds=1.25,
        audio_seconds=10.0,
        samples=441000,
        stems=[Stem(name="drums", path="drums.wav", samples=441000)],
    )
    assert StemSet.model_validate_json(original.model_dump_json()) == original


def _synthetic_mix(seconds: int = 12) -> np.ndarray:
    """Low sine bursts on beats, a sustained 440 Hz tone and noise bursts, stereo float32."""
    n = seconds * SAMPLE_RATE
    t = np.arange(n) / SAMPLE_RATE
    rng = np.random.default_rng(1)
    mono = 0.15 * np.sin(2 * np.pi * 440 * t)
    burst_t = np.arange(int(0.15 * SAMPLE_RATE)) / SAMPLE_RATE
    kick = 0.6 * np.sin(2 * np.pi * 60 * burst_t) * np.exp(-burst_t / 0.05)
    for beat in np.arange(0.0, seconds - 0.2, 0.5):
        start = int(beat * SAMPLE_RATE)
        mono[start : start + kick.size] += kick
    for burst in np.arange(0.25, seconds - 0.2, 1.0):
        start = int(burst * SAMPLE_RATE)
        length = int(0.05 * SAMPLE_RATE)
        mono[start : start + length] += 0.2 * rng.standard_normal(length)
    return np.stack([mono, 0.9 * mono]).astype(np.float32)


# Measured -23.6 dB on this synthetic mix with htdemucs_ft on CPU. Demucs predicts each stem as a
# waveform (not a mask), so the sum only approximates the input; -20 dB leaves ~3.6 dB of margin.
RESIDUAL_LIMIT_DB = -20.0


@pytest.mark.slow
def test_separate_htdemucs_ft_cpu(tmp_path: Path) -> None:
    """Runs the real htdemucs_ft bag on CPU; downloads weights on first run.

    Asserts four stems with exactly the input sample count and that the stem sum reconstructs the
    input with a relative residual below RESIDUAL_LIMIT_DB.
    """
    mix = _synthetic_mix()
    result = separate(mix, "synthetic", model="htdemucs_ft", out_dir=tmp_path, device="cpu")

    assert [s.name for s in result.stems] == list(ALLOWED_MODELS["htdemucs_ft"])
    total = np.zeros_like(mix, dtype=np.float64)
    for stem in result.stems:
        data, rate = sf.read(str(tmp_path / stem.path), dtype="float32", always_2d=True)
        assert rate == SAMPLE_RATE
        assert data.shape == (mix.shape[-1], 2)
        assert stem.samples == mix.shape[-1]
        total += data.T
    residual = total - mix
    rms = lambda x: math.sqrt(float(np.mean(np.square(x, dtype=np.float64))))  # noqa: E731
    residual_db = 20 * math.log10(rms(residual) / rms(mix))
    assert residual_db < RESIDUAL_LIMIT_DB
    assert result.model.name == "htdemucs_ft"
    assert result.audio_seconds == pytest.approx(12.0)


@pytest.mark.slow
@requires_ffmpeg
def test_separate_cli_writes_stemset(sine_wav: Path, tmp_path: Path) -> None:
    from typer.testing import CliRunner

    out = tmp_path / "out"
    result = CliRunner().invoke(
        app, ["separate", str(sine_wav), "--out", str(out), "--model", "htdemucs_ft"]
    )
    assert result.exit_code == 0, result.output
    stemset = StemSet.model_validate_json((out / "stemset.json").read_text(encoding="utf-8"))
    assert len(stemset.stems) == 4
    assert re.search(r"ratio \d+\.\d+", result.output)
