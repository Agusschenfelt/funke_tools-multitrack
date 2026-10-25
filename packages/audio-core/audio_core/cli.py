"""Command line interface."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypeVar

import typer
from pydantic import BaseModel
from rich.console import Console

from audio_core.analysis import AnalysisError, AnalyzeOptions
from audio_core.analysis import analyze as run_analyze
from audio_core.io import DecodeError, decode
from audio_core.models import Analysis, StemSet
from audio_core.separation import DEFAULT_MODEL, SeparationError
from audio_core.separation import separate as run_separate

app = typer.Typer(help="Audio pipelines for the multitrack and stems tool.", no_args_is_help=True)
console = Console()

InputArg = Annotated[Path, typer.Argument(help="Input audio file.")]
OutOpt = Annotated[Path, typer.Option("--out", help="Output directory.")]

T = TypeVar("T")


def _run_or_exit(step: Callable[[], T], name: str) -> T:
    """Run a pipeline step, translating known failures into CLI exit codes."""
    try:
        return step()
    except (DecodeError, AnalysisError, SeparationError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except NotImplementedError as exc:
        typer.echo(f"{name} is not implemented yet: {exc}", err=True)
        raise typer.Exit(code=2) from exc


def _write_json(result: BaseModel, out: Path, filename: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    path = out / filename
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"Wrote {path}")


def _summary(result: Analysis) -> str:
    parts = []
    if result.grid:
        parts.append(f"BPM {result.grid.bpm:g}")
        parts.append(result.grid.time_signature)
    if result.key and result.key.camelot:
        parts.append(f"{result.key.key} {result.key.mode}")
        parts.append(f"Camelot {result.key.camelot}")
    elif result.key:
        parts.append("key unknown")
    if result.loudness:
        parts.append(f"{result.loudness.integrated_lufs:.1f} LUFS")
    return " | ".join(parts)


def _separation_summary(result: StemSet) -> str:
    ratio = result.elapsed_seconds / result.audio_seconds if result.audio_seconds else 0.0
    return (
        f"{result.model.name} | {result.device} | {result.elapsed_seconds:.1f} s elapsed | "
        f"{result.audio_seconds:.1f} s audio | ratio {ratio:.2f} (elapsed/audio)"
    )


@app.command()
def analyze(
    input: InputArg,
    out: OutOpt,
    key_backend: Annotated[
        str, typer.Option("--key-backend", help="Key estimator: auto, essentia or librosa.")
    ] = "auto",
) -> None:
    """Analyze tempo grid, key and loudness; writes analysis.json."""
    options = AnalyzeOptions(key_backend=key_backend)  # type: ignore[arg-type]
    audio = _run_or_exit(lambda: decode(input), "decode")
    result = _run_or_exit(lambda: run_analyze(audio, str(input), options=options), "analyze")
    _write_json(result, out, "analysis.json")
    console.print(_summary(result), markup=False, highlight=False)


@app.command()
def separate(
    input: InputArg,
    out: OutOpt,
    model: Annotated[str, typer.Option(help="Separation model name.")] = DEFAULT_MODEL,
    device: Annotated[str, typer.Option(help="Torch device: cpu, cuda or mps.")] = "cpu",
    shifts: Annotated[int, typer.Option(help="Random shifts averaged (1 = fastest).")] = 1,
) -> None:
    """Separate stems; writes one WAV per stem and stemset.json."""
    audio = _run_or_exit(lambda: decode(input), "decode")
    result = _run_or_exit(
        lambda: run_separate(
            audio, str(input), model=model, out_dir=out, device=device, shifts=shifts
        ),
        "separate",
    )
    _write_json(result, out, "stemset.json")
    console.print(_separation_summary(result), markup=False, highlight=False)
