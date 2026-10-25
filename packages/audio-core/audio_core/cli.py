"""Command line interface."""

from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel

from audio_core.analysis import analyze as run_analyze
from audio_core.io import DecodeError, decode
from audio_core.separation import separate as run_separate

app = typer.Typer(help="Audio pipelines for the multitrack and stems tool.", no_args_is_help=True)

InputArg = Annotated[Path, typer.Argument(help="Input audio file.")]
OutOpt = Annotated[Path, typer.Option("--out", help="Output directory.")]


def _decode_or_exit(path: Path):
    try:
        return decode(path)
    except DecodeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _write_json(result: BaseModel, path: Path) -> None:
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"Wrote {path}")


@app.command()
def analyze(input: InputArg, out: OutOpt) -> None:
    """Analyze tempo grid, key and loudness; writes analysis.json."""
    audio = _decode_or_exit(input)
    out.mkdir(parents=True, exist_ok=True)
    try:
        result = run_analyze(audio, str(input))
    except NotImplementedError as exc:
        typer.echo(f"analyze is not implemented yet: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    _write_json(result, out / "analysis.json")


@app.command()
def separate(
    input: InputArg,
    out: OutOpt,
    model: Annotated[str, typer.Option(help="Separation model name.")] = "htdemucs_6s",
) -> None:
    """Separate stems; writes one WAV per stem and stemset.json."""
    audio = _decode_or_exit(input)
    out.mkdir(parents=True, exist_ok=True)
    try:
        result = run_separate(audio, str(input), model=model, out_dir=out)
    except NotImplementedError as exc:
        typer.echo(f"separate is not implemented yet: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    _write_json(result, out / "stemset.json")
