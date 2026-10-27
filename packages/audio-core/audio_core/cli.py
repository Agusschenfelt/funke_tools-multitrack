"""Command line interface."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypeVar

import typer
from pydantic import BaseModel
from rich.console import Console

from audio_core.analysis import AnalysisError, AnalyzeOptions
from audio_core.analysis import analyze as run_analyze
from audio_core.guide import CueLibraryError
from audio_core.io import DecodeError, decode
from audio_core.models import Analysis, Sections, StagePackOptions, StemSet
from audio_core.separation import DEFAULT_MODEL, SeparationError
from audio_core.separation import separate as run_separate
from audio_core.stagepack import StagePackError, build_stagepack, load_json_model

app = typer.Typer(help="Audio pipelines for the multitrack and stems tool.", no_args_is_help=True)
console = Console()

InputArg = Annotated[Path, typer.Argument(help="Input audio file.")]
OutOpt = Annotated[Path, typer.Option("--out", help="Output directory.")]

T = TypeVar("T")


def _run_or_exit(step: Callable[[], T], name: str) -> T:
    """Run a pipeline step, translating known failures into CLI exit codes."""
    try:
        return step()
    except (DecodeError, AnalysisError, SeparationError, StagePackError, CueLibraryError) as exc:
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
    shifts: Annotated[
        int, typer.Option(help="Random shifts averaged (0 = fastest, deterministic).")
    ] = 1,
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


@app.command()
def stagepack(
    stemset_dir: Annotated[Path, typer.Argument(help="Directory with stemset.json and stem WAVs.")],
    out: OutOpt,
    analysis: Annotated[Path, typer.Option("--analysis", help="analysis.json from analyze.")],
    sections: Annotated[
        Path | None, typer.Option("--sections", help="Optional sections.json.")
    ] = None,
    destination: Annotated[str, typer.Option(help="playback or daw.")] = "playback",
    count_in: Annotated[int, typer.Option("--count-in", help="Count-in bars: 1 or 2.")] = 1,
    click_sound: Annotated[
        str, typer.Option("--click-sound", help="classic, cowbell, woodblock or rimshot.")
    ] = "classic",
    subdivision: Annotated[str, typer.Option(help="quarter or eighth.")] = "quarter",
    straight_grid: Annotated[
        bool, typer.Option("--straight-grid", help="Click on an even grid at the mean tempo.")
    ] = False,
    sample_rate: Annotated[
        int, typer.Option("--sample-rate", help="Export rate: 44100 or 48000.")
    ] = 44100,
    include_vocals: Annotated[
        bool, typer.Option("--include-vocals", help="Keep the lead vocal in the pack.")
    ] = False,
    language: Annotated[str, typer.Option(help="Guide and text language: es or en.")] = "es",
    cues_dir: Annotated[
        Path | None, typer.Option("--cues-dir", help="Cue sample library directory.")
    ] = None,
) -> None:
    """Build the Stage Pack ZIP from stems, analysis and optional sections."""
    try:
        options = StagePackOptions(
            destination=destination,  # type: ignore[arg-type]
            count_in_bars=count_in,  # type: ignore[arg-type]
            click_sound=click_sound,  # type: ignore[arg-type]
            subdivision=subdivision,  # type: ignore[arg-type]
            straight_grid=straight_grid,
            sample_rate=sample_rate,  # type: ignore[arg-type]
            include_vocals=include_vocals,
            language=language,  # type: ignore[arg-type]
        )
    except ValueError as exc:
        typer.echo(f"Error: invalid option: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    def build():
        stemset = load_json_model(stemset_dir / "stemset.json", StemSet, "stemset.json")
        loaded_analysis = load_json_model(analysis, Analysis, "analysis")
        loaded_sections = (
            load_json_model(sections, Sections, "sections") if sections is not None else None
        )
        return build_stagepack(
            stemset, stemset_dir, loaded_analysis, loaded_sections, options, out, cues_dir
        )

    result = _run_or_exit(build, "stagepack")
    for warning in result.report["guide_warnings"]:
        typer.echo(f"Warning: {warning}", err=True)
    typer.echo(f"Wrote {result.zip_path}")
