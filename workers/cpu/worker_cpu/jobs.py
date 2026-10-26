"""RQ job functions. Arguments and results are JSON-serializable.

Jobs call the audio-core library functions the same way ``audio_core.cli`` does and move files
through ``Storage``; audio work happens in a private temporary directory. Each job reports its
progress in ``job.meta["stage"]`` (a no-op when run outside an RQ job).

Stages:

* ``analyze_job``: decoding, analyzing (beats, key and loudness run inside one library call),
  sections, saving, done. Section files: ``sections.detected.json`` always holds the latest
  detector output; ``sections.json`` is what users read and edit, so it is written only when it
  does not exist yet or when ``overwrite_sections=True`` is passed explicitly.
* ``separate_job``: decoding, separating, saving, done.
* ``stagepack_job``: loading, packing, saving, done.

Every job also keeps two small markers in the song's storage (only when run by RQ, so the job id
is known): ``jobs/<job_id>.lock`` while it runs (cleanup never deletes a song with a live lock) and
``jobs/<job_id>.json`` with its return value once it succeeded. The API reads that result marker,
and only that, to recover the outcome of a job RQ has forgotten.
"""

import functools
import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from audio_core.analysis import AnalyzeOptions
from audio_core.analysis import analyze as run_analyze
from audio_core.io import decode
from audio_core.models import Analysis, Sections, StagePackOptions, StemSet
from audio_core.sections import detect_sections, sections_model_version
from audio_core.separation import DEFAULT_MODEL
from audio_core.separation import separate as run_separate
from audio_core.stagepack import build_stagepack
from rq import get_current_job

from worker_cpu.config import cues_dir, get_storage
from worker_cpu.storage import (
    ANALYSIS,
    JOBS_PREFIX,
    LOCK_SUFFIX,
    PACKS_PREFIX,
    SECTIONS,
    SECTIONS_DETECTED,
    SOURCE_PREFIX,
    STEMS_PREFIX,
    STEMSET,
    Storage,
    StorageError,
)


class JobError(RuntimeError):
    """Raised when a job cannot run because an input is missing or invalid."""


def set_stage(stage: str) -> None:
    """Record the current stage on the running RQ job; no-op without a job context."""
    job = get_current_job()
    if job is None:
        return
    job.meta["stage"] = stage
    job.save_meta()


def tracked(func: Callable[..., Any]) -> Callable[..., Any]:
    """Lock the song while the job runs and record its result under ``jobs/<job_id>.json``.

    The result marker is written after the artifacts and before the job returns, so a marker
    proves its own job succeeded. Failed jobs write none. Outside an RQ job nothing is written.
    """

    @functools.wraps(func)
    def wrapper(song_id: str, *args: Any, **kwargs: Any) -> Any:
        job_id = getattr(get_current_job(), "id", None)
        if not job_id:
            return func(song_id, *args, **kwargs)
        storage = get_storage()
        lock = f"{JOBS_PREFIX}{job_id}{LOCK_SUFFIX}"
        storage.put_bytes(song_id, lock, b"")
        try:
            result = func(song_id, *args, **kwargs)
            storage.put_bytes(
                song_id, f"{JOBS_PREFIX}{job_id}.json", json.dumps({"result": result}).encode()
            )
            return result
        finally:
            storage.delete(song_id, lock)

    return wrapper


def _source_name(storage: Storage, song_id: str) -> str:
    """The single stored ``source.<ext>`` file; none or several is an error."""
    names = [n for n in storage.list_names(song_id, SOURCE_PREFIX + ".") if "/" not in n]
    if not names:
        raise JobError(f"no source audio stored for song {song_id}")
    if len(names) > 1:
        raise JobError(f"ambiguous source audio for song {song_id}: {', '.join(names)}")
    return names[0]


def _decode_source(storage: Storage, song_id: str, workdir: Path) -> tuple[Any, str]:
    name = _source_name(storage, song_id)
    local = workdir / name
    storage.get_file(song_id, name, local)
    return decode(local), name


@tracked
def analyze_job(
    song_id: str,
    *,
    sections: bool = True,
    source_name: str | None = None,
    overwrite_sections: bool = False,
) -> dict:
    """Decode the stored source, analyze it and (optionally) detect sections.

    ``source_name`` is the label written into the JSON ``source`` fields (and so the Stage Pack
    title); it defaults to the stored file name.

    Sections: with ``sections=True`` the detector output is always saved as
    ``sections.detected.json``; ``sections.json`` (the user-facing, editable file) is written only
    when absent or when ``overwrite_sections`` is true, so a re-run never silently replaces edits.
    With ``sections=False`` neither file is touched. A detection failure raises before anything
    is saved, so a failed run changes no file. The song id is derived from the audio hash, so an
    existing ``sections.json`` always describes the same audio.
    """
    storage = get_storage()
    with tempfile.TemporaryDirectory(prefix="worker-cpu-") as tmp:
        set_stage("decoding")
        audio, stored_name = _decode_source(storage, song_id, Path(tmp))
        label = source_name or stored_name
        set_stage("analyzing")
        analysis = run_analyze(audio, label, options=AnalyzeOptions())
        detected = None
        if sections:
            set_stage("sections")
            if analysis.grid is None:
                raise JobError("analysis has no beat grid; cannot detect sections")
            detected = detect_sections(audio, analysis.grid, source=label)
            analysis.models["sections"] = sections_model_version()
        set_stage("saving")
        storage.put_bytes(song_id, ANALYSIS, analysis.model_dump_json(indent=2).encode())
        overwritten = False
        if detected is not None:
            payload = detected.model_dump_json(indent=2).encode()
            storage.put_bytes(song_id, SECTIONS_DETECTED, payload)
            if overwrite_sections or not storage.exists(song_id, SECTIONS):
                overwritten = storage.exists(song_id, SECTIONS)
                storage.put_bytes(song_id, SECTIONS, payload)
    set_stage("done")
    grid = analysis.grid
    return {
        "song_id": song_id,
        "analysis": ANALYSIS,
        "sections": SECTIONS if storage.exists(song_id, SECTIONS) else None,
        "sections_detected": SECTIONS_DETECTED if detected is not None else None,
        "sections_overwritten": overwritten,
        "bpm": grid.bpm if grid else None,
        "section_count": len(detected.sections) if detected is not None else 0,
    }


@tracked
def separate_job(song_id: str, model: str = DEFAULT_MODEL, source_name: str | None = None) -> dict:
    """Separate the stored source into stems stored under ``stems/`` with ``stemset.json``."""
    storage = get_storage()
    with tempfile.TemporaryDirectory(prefix="worker-cpu-") as tmp:
        workdir = Path(tmp)
        set_stage("decoding")
        audio, stored_name = _decode_source(storage, song_id, workdir)
        set_stage("separating")
        stems_dir = workdir / "stems"
        result = run_separate(
            audio, source_name or stored_name, model=model, out_dir=stems_dir, device="cpu"
        )
        (stems_dir / "stemset.json").write_text(result.model_dump_json(indent=2), "utf-8")
        set_stage("saving")
        for stem in result.stems:
            storage.put_file(song_id, f"{STEMS_PREFIX}{stem.path}", stems_dir / stem.path)
        storage.put_file(song_id, STEMSET, stems_dir / "stemset.json")
    set_stage("done")
    return {
        "song_id": song_id,
        "model": result.model.name,
        "stems": [stem.name for stem in result.stems],
    }


def _fetch_stems(storage: Storage, song_id: str, stems_dir: Path) -> StemSet:
    try:
        stemset = StemSet.model_validate_json(storage.get_bytes(song_id, STEMSET))
    except StorageError as exc:
        raise JobError(f"no stems stored for song {song_id}; run separation first") from exc
    for stem in stemset.stems:
        storage.get_file(song_id, f"{STEMS_PREFIX}{stem.path}", stems_dir / stem.path)
    return stemset


@tracked
def stagepack_job(song_id: str, options: dict[str, Any]) -> str:
    """Build a Stage Pack from stored stems, analysis and sections; returns the ZIP name."""
    try:
        pack_options = StagePackOptions(**options)
    except ValueError as exc:
        raise JobError(f"invalid stagepack options: {exc}") from exc
    storage = get_storage()
    with tempfile.TemporaryDirectory(prefix="worker-cpu-") as tmp:
        workdir = Path(tmp)
        set_stage("loading")
        stems_dir = workdir / "stems"
        stems_dir.mkdir()
        stemset = _fetch_stems(storage, song_id, stems_dir)
        try:
            analysis = Analysis.model_validate_json(storage.get_bytes(song_id, ANALYSIS))
        except StorageError as exc:
            raise JobError(f"no analysis stored for song {song_id}; run analysis first") from exc
        sections = (
            Sections.model_validate_json(storage.get_bytes(song_id, SECTIONS))
            if storage.exists(song_id, SECTIONS)
            else None
        )
        set_stage("packing")
        out_dir = workdir / "out"
        result = build_stagepack(
            stemset, stems_dir, analysis, sections, pack_options, out_dir, cues_dir()
        )
        set_stage("saving")
        pack_name = result.zip_path.name
        storage.put_file(song_id, f"{PACKS_PREFIX}{pack_name}", result.zip_path)
    set_stage("done")
    return pack_name
