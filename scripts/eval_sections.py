"""Evaluate section detection against hand-made annotations.

Run from the repository root:

    uv run --project packages/audio-core python scripts/eval_sections.py <songs dir> --out <dir>

Per song the directory holds ``<name>.<audio ext>`` and ``<name>.sections.json`` (the annotation, in
the ``sections.json`` schema), and optionally ``<name>.analysis.json`` (reused instead of analyzing
again) and ``<name>.stems/`` (a stem set directory; its vocals stem is passed to detection).

Metric conventions:

* Boundary hit rate (HR.5F, HR3F): a detected boundary is a hit when it lies within the tolerance
  (0.5 s or 3 s) of a still unmatched annotated boundary; matching is one-to-one. Precision is
  hits / detected, recall is hits / annotated, F is their harmonic mean. The song start (the first
  section start of each side) is not a boundary and is excluded from both sides. When both sides
  have no boundary left the score is 1.0; when only one does, it is 0.0.
* Per-bar label accuracy: each bar of the grid takes the label of the section that contains its
  midpoint; accuracy is the fraction of bars where detected and annotated labels are equal. The
  relaxed variant maps ``verse_2`` to ``verse`` on both sides first.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.table import Table

from audio_core.analysis import AnalyzeOptions
from audio_core.analysis import analyze as run_analyze
from audio_core.io import decode, duration_seconds
from audio_core.models import Analysis, Grid, Sections, StemSet
from audio_core.sections import (
    bar_edges,
    detect_sections,
    load_vocal_stem,
    sections_model_version,
)
from audio_core.stagepack import load_json_model

AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aiff", ".aif")
TOLERANCES = {"hr_05": 0.5, "hr_3": 3.0}
RELAXED = {"verse_2": "verse"}
METRIC_KEYS = (
    "hr_05_precision", "hr_05_recall", "hr_05_f",
    "hr_3_precision", "hr_3_recall", "hr_3_f",
    "label_accuracy", "label_accuracy_relaxed",
)  # fmt: skip


def boundary_times(sections: Sections) -> list[float]:
    """Interior boundaries: every section start except the first (the song start)."""
    return [section.start for section in sections.sections[1:]]


def count_hits(reference: list[float], estimate: list[float], tolerance: float) -> int:
    """One-to-one matches within ``tolerance`` seconds; greedy on sorted times is optimal in 1-D."""
    ref, est = sorted(reference), sorted(estimate)
    i = j = hits = 0
    while i < len(ref) and j < len(est):
        if abs(ref[i] - est[j]) <= tolerance:
            hits += 1
            i += 1
            j += 1
        elif est[j] < ref[i]:
            j += 1
        else:
            i += 1
    return hits


def hit_rate(reference: list[float], estimate: list[float], tolerance: float) -> dict[str, float]:
    """Boundary precision, recall and F at ``tolerance`` seconds."""
    if not reference and not estimate:
        return {"precision": 1.0, "recall": 1.0, "f": 1.0}
    hits = count_hits(reference, estimate, tolerance)
    precision = hits / len(estimate) if estimate else 0.0
    recall = hits / len(reference) if reference else 0.0
    f = 2 * precision * recall / (precision + recall) if hits else 0.0
    return {"precision": precision, "recall": recall, "f": f}


def label_at(sections: Sections, time: float, *, relaxed: bool = False) -> str | None:
    """Name of the section containing ``time``; None before the first section starts."""
    name = None
    for section in sections.sections:
        if section.start > time:
            break
        name = section.name.value
    if relaxed and name is not None:
        name = RELAXED.get(name, name)
    return name


def label_accuracy(
    reference: Sections, estimate: Sections, edges: list[float], *, relaxed: bool = False
) -> float:
    """Fraction of bars (given by ``edges``) whose midpoint labels agree."""
    midpoints = [(a + b) / 2 for a, b in zip(edges[:-1], edges[1:], strict=False)]
    if not midpoints:
        return 0.0
    same = sum(
        label_at(reference, mid, relaxed=relaxed) == label_at(estimate, mid, relaxed=relaxed)
        for mid in midpoints
    )
    return same / len(midpoints)


def song_metrics(reference: Sections, estimate: Sections, edges: list[float]) -> dict[str, float]:
    """All metrics for one song, keyed as in ``METRIC_KEYS``."""
    ref_times, est_times = boundary_times(reference), boundary_times(estimate)
    metrics: dict[str, float] = {}
    for prefix, tolerance in TOLERANCES.items():
        for key, value in hit_rate(ref_times, est_times, tolerance).items():
            metrics[f"{prefix}_{key}"] = value
    metrics["label_accuracy"] = label_accuracy(reference, estimate, edges)
    metrics["label_accuracy_relaxed"] = label_accuracy(reference, estimate, edges, relaxed=True)
    return metrics


def macro_average(rows: list[dict[str, float]]) -> dict[str, float]:
    """Unweighted mean of each metric over songs; empty input gives an empty dict."""
    if not rows:
        return {}
    return {key: sum(row[key] for row in rows) / len(rows) for key in METRIC_KEYS}


def find_audio(directory: Path, name: str) -> Path | None:
    for extension in AUDIO_EXTENSIONS:
        candidate = directory / f"{name}{extension}"
        if candidate.is_file():
            return candidate
    return None


def song_names(directory: Path) -> list[str]:
    suffix = ".sections.json"
    return sorted(p.name[: -len(suffix)] for p in directory.glob(f"*{suffix}"))


def evaluate_song(directory: Path, name: str) -> dict:
    """Detect sections for one song of the directory and score them against its annotation."""
    audio_path = find_audio(directory, name)
    if audio_path is None:
        raise FileNotFoundError(f"no audio file named {name}.<ext> in {directory}")
    reference = load_json_model(directory / f"{name}.sections.json", Sections, "annotation")
    audio = decode(audio_path)
    duration = duration_seconds(audio)

    analysis_path = directory / f"{name}.analysis.json"
    if analysis_path.is_file():
        grid: Grid | None = load_json_model(analysis_path, Analysis, "analysis").grid
    else:
        grid = run_analyze(audio, str(audio_path), options=AnalyzeOptions()).grid
    if grid is None:
        raise ValueError("analysis has no beat grid")

    vocals = None
    stems_dir = directory / f"{name}.stems"
    with_vocals = stems_dir.is_dir()
    if with_vocals:
        stemset = load_json_model(stems_dir / "stemset.json", StemSet, "stemset.json")
        vocals = load_vocal_stem(stemset, stems_dir)

    estimate = detect_sections(audio, grid, vocals=vocals, source=str(audio_path))
    edges = [float(edge) for edge in bar_edges(grid, duration)]
    return {
        "name": name,
        "vocals": with_vocals,
        "bars": len(edges) - 1,
        "reference_boundaries": len(boundary_times(reference)),
        "detected_boundaries": len(boundary_times(estimate)),
        "metrics": song_metrics(reference, estimate, edges),
    }


def evaluate_directory(directory: Path) -> dict:
    """Evaluate every annotated song; a failing song is reported with its error, not fatal."""
    songs = []
    for name in song_names(directory):
        try:
            songs.append(evaluate_song(directory, name))
        except Exception as exc:  # noqa: BLE001 - one bad song must not hide the others
            songs.append({"name": name, "error": f"{type(exc).__name__}: {exc}"})
    scored = [song["metrics"] for song in songs if "metrics" in song]
    version = sections_model_version()
    return {
        "date": date.today().isoformat(),
        "sections_model": version.model_dump(),
        "songs": songs,
        "macro_average": macro_average(scored),
    }


def print_report(report: dict, console: Console) -> None:
    table = Table(title="Section detection evaluation")
    table.add_column("song")
    for header in ("HR.5 P", "HR.5 R", "HR.5 F", "HR3 P", "HR3 R", "HR3 F", "label", "label~"):
        table.add_column(header, justify="right")
    table.add_column("bars", justify="right")
    for song in report["songs"]:
        if "error" in song:
            table.add_row(song["name"], f"error: {song['error']}")
            continue
        values = [f"{song['metrics'][key]:.2f}" for key in METRIC_KEYS]
        table.add_row(song["name"], *values, str(song["bars"]))
    if report["macro_average"]:
        table.add_section()
        values = [f"{report['macro_average'][key]:.2f}" for key in METRIC_KEYS]
        table.add_row("macro average", *values, "")
    console.print(table)
    console.print("label~ = relaxed accuracy (verse_2 counts as verse)", markup=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("songs", type=Path, help="Directory with audio and *.sections.json files.")
    parser.add_argument(
        "--out", type=Path, default=None, help="Directory for eval_report.json (default: songs)."
    )
    args = parser.parse_args(argv)
    if not args.songs.is_dir():
        print(f"Error: not a directory: {args.songs}", file=sys.stderr)
        return 1
    if not song_names(args.songs):
        print(f"Error: no *.sections.json annotations in {args.songs}", file=sys.stderr)
        return 1
    report = evaluate_directory(args.songs)
    out = args.out or args.songs
    out.mkdir(parents=True, exist_ok=True)
    path = out / "eval_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print_report(report, Console())
    print(f"Wrote {path}")
    return 0 if all("error" not in song for song in report["songs"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
