import io
import json
import zipfile
from pathlib import Path

import pytest
import soundfile as sf
from audio_core.models import Analysis, Sections, StemSet
from rq.job import JobStatus

from tests.conftest import STEM_NAMES, StageRecorder, requires_ffmpeg
from worker_cpu import jobs
from worker_cpu.storage import LocalStorage

pytestmark = requires_ffmpeg


def test_analyze_job_writes_both_jsons_and_reports_stages(
    song: str, storage: LocalStorage, fake_models: None, recorder: StageRecorder
) -> None:
    result = jobs.analyze_job(song)
    assert recorder.stages == ["decoding", "analyzing", "sections", "saving", "done"]
    analysis = Analysis.model_validate_json(storage.get_bytes(song, "analysis.json"))
    sections = Sections.model_validate_json(storage.get_bytes(song, "sections.json"))
    assert analysis.source == "source.wav"
    assert "sections" in analysis.models
    assert len(sections.sections) >= 1
    assert result == {
        "song_id": song,
        "analysis": "analysis.json",
        "sections": "sections.json",
        "bpm": 120.0,
        "section_count": len(sections.sections),
    }
    json.dumps(result)


def test_analyze_job_without_sections(
    song: str, storage: LocalStorage, fake_models: None, recorder: StageRecorder
) -> None:
    result = jobs.analyze_job(song, sections=False, source_name="Mi Cancion.mp3")
    assert recorder.stages == ["decoding", "analyzing", "saving", "done"]
    assert not storage.exists(song, "sections.json")
    assert result["sections"] is None
    analysis = Analysis.model_validate_json(storage.get_bytes(song, "analysis.json"))
    assert analysis.source == "Mi Cancion.mp3"


def test_jobs_run_without_a_job_context(song: str, fake_models: None) -> None:
    assert jobs.analyze_job(song)["bpm"] == 120.0


def test_analyze_job_without_source_fails(storage_root: Path, fake_models: None) -> None:
    with pytest.raises(jobs.JobError, match="no source audio"):
        jobs.analyze_job("ghost")


def test_separate_job_stores_stems_and_stemset(
    song: str, storage: LocalStorage, fake_models: None, recorder: StageRecorder
) -> None:
    result = jobs.separate_job(song, model="htdemucs_6s")
    assert recorder.stages == ["decoding", "separating", "saving", "done"]
    assert result == {"song_id": song, "model": "htdemucs_6s", "stems": list(STEM_NAMES)}
    stemset = StemSet.model_validate_json(storage.get_bytes(song, "stems/stemset.json"))
    assert [s.name for s in stemset.stems] == list(STEM_NAMES)
    for name in STEM_NAMES:
        assert storage.exists(song, f"stems/{name}.wav")


def test_stagepack_job_requires_stems_and_analysis(song: str, fake_models: None) -> None:
    with pytest.raises(jobs.JobError, match="run separation first"):
        jobs.stagepack_job(song, {"destination": "daw"})
    jobs.separate_job(song)
    with pytest.raises(jobs.JobError, match="run analysis first"):
        jobs.stagepack_job(song, {"destination": "daw"})


def test_stagepack_job_rejects_invalid_options(song: str, fake_models: None) -> None:
    with pytest.raises(jobs.JobError, match="invalid stagepack options"):
        jobs.stagepack_job(song, {"destination": "vinyl"})


def test_full_pipeline_builds_equal_length_pack(
    song: str, storage: LocalStorage, fake_models: None, recorder: StageRecorder
) -> None:
    jobs.analyze_job(song, source_name="Mi Cancion.wav")
    jobs.separate_job(song, source_name="Mi Cancion.wav")
    recorder.stages.clear()
    name = jobs.stagepack_job(song, {"destination": "daw", "sample_rate": 48000})
    assert recorder.stages == ["loading", "packing", "saving", "done"]
    assert name.endswith(".zip")
    assert storage.list_names(song, "packs/") == [f"packs/{name}"]
    with zipfile.ZipFile(io.BytesIO(storage.get_bytes(song, f"packs/{name}"))) as archive:
        wavs = [n for n in archive.namelist() if n.endswith(".wav")]
        frames = {sf.info(io.BytesIO(archive.read(n))).frames for n in wavs}
        assert len(wavs) >= len(STEM_NAMES) + 2
        assert len(frames) == 1
        assert "Secciones.txt" in archive.namelist()


def test_jobs_run_through_an_rq_queue(
    song: str, storage: LocalStorage, fake_models: None, queue
) -> None:
    analyze = queue.enqueue(jobs.analyze_job, song)
    separate = queue.enqueue(jobs.separate_job, song)
    pack = queue.enqueue(jobs.stagepack_job, song, {"destination": "playback"})
    for job in (analyze, separate, pack):
        assert job.get_status() == JobStatus.FINISHED
        assert job.meta["stage"] == "done"
    assert analyze.return_value()["section_count"] >= 1
    assert pack.return_value() == storage.list_names(song, "packs/")[0].removeprefix("packs/")


def test_failed_job_is_recorded_by_the_queue(storage_root: Path, fake_models: None, queue) -> None:
    job = queue.enqueue(jobs.analyze_job, "ghost")
    assert job.get_status() == JobStatus.FAILED
    assert "no source audio" in job.latest_result().exc_string
