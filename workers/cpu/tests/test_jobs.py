import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from audio_core.constants import PREVIEW_PRIMING_SAMPLES, SAMPLE_RATE
from audio_core.io import DecodeError, decode
from audio_core.models import Analysis, Sections, StemSet
from rq.job import JobStatus

from tests.conftest import STEM_NAMES, StageRecorder, requires_ffmpeg
from worker_cpu import jobs
from worker_cpu.storage import LocalStorage


@requires_ffmpeg
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
        "sections_detected": "sections.detected.json",
        "sections_overwritten": False,
        "bpm": 120.0,
        "section_count": len(sections.sections),
    }
    json.dumps(result)


@requires_ffmpeg
def test_analyze_job_without_sections(
    song: str, storage: LocalStorage, fake_models: None, recorder: StageRecorder
) -> None:
    result = jobs.analyze_job(song, sections=False, source_name="Mi Cancion.mp3")
    assert recorder.stages == ["decoding", "analyzing", "saving", "done"]
    assert not storage.exists(song, "sections.json")
    assert result["sections"] is None
    analysis = Analysis.model_validate_json(storage.get_bytes(song, "analysis.json"))
    assert analysis.source == "Mi Cancion.mp3"


@requires_ffmpeg
def test_jobs_run_without_a_job_context(song: str, fake_models: None) -> None:
    assert jobs.analyze_job(song)["bpm"] == 120.0


def test_analyze_job_without_source_fails(storage_root: Path, fake_models: None) -> None:
    with pytest.raises(jobs.JobError, match="no source audio"):
        jobs.analyze_job("ghost")


@requires_ffmpeg
def test_separate_job_stores_stems_and_stemset(
    song: str, storage: LocalStorage, fake_models: None, recorder: StageRecorder
) -> None:
    result = jobs.separate_job(song, model="htdemucs_6s")
    assert recorder.stages == ["decoding", "separating", "previews", "saving", "done"]
    assert result == {
        "song_id": song,
        "model": "htdemucs_6s",
        "stems": list(STEM_NAMES),
        "previews": True,
    }
    stemset = StemSet.model_validate_json(storage.get_bytes(song, "stems/stemset.json"))
    assert [s.name for s in stemset.stems] == list(STEM_NAMES)
    assert stemset.preview is not None and stemset.preview.priming_samples == 1024
    for name in STEM_NAMES:
        assert storage.exists(song, f"stems/{name}.wav")
        assert storage.exists(song, f"stems/preview/{name}.m4a")


def _lag_samples(reference: np.ndarray, other: np.ndarray, window: int = 2048) -> int:
    """Samples ``other`` is late relative to ``reference`` (FFT cross-correlation, +-window)."""
    n = min(len(reference), len(other))
    size = 1 << (2 * n - 1).bit_length()
    corr = np.fft.irfft(
        np.fft.rfft(other[:n], size) * np.conj(np.fft.rfft(reference[:n], size)), size
    )
    lags = np.concatenate([np.arange(0, window + 1), np.arange(-window, 0)])
    scores = np.concatenate([corr[: window + 1], corr[size - window :]])
    return int(lags[int(np.argmax(scores))])


@requires_ffmpeg
def test_previews_are_aligned_with_the_wav_stems(
    song: str, storage: LocalStorage, fake_models: None, tmp_path: Path
) -> None:
    """Every preview decodes to the stem's length and lines up with it (lag 0 samples)."""
    jobs.separate_job(song)
    for name in ("drums", "vocals"):
        wav, preview = tmp_path / f"{name}.wav", tmp_path / f"{name}.m4a"
        storage.get_file(song, f"stems/{name}.wav", wav)
        storage.get_file(song, f"stems/preview/{name}.m4a", preview)
        original, decoded = decode(wav), decode(preview)
        # ffmpeg honors the edit list: the encoder delay is gone, at most a frame of padding stays.
        assert 0 <= decoded.shape[-1] - original.shape[-1] < PREVIEW_PRIMING_SAMPLES
        assert _lag_samples(original[0], decoded[0]) == 0


@requires_ffmpeg
def test_separate_job_keeps_wav_stems_when_preview_encoding_fails(
    song: str,
    storage: LocalStorage,
    fake_models: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def flaky(source: Path, target: Path, *args, **kwargs) -> None:
        calls.append(target)
        if len(calls) == 3:
            raise DecodeError("boom")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")

    monkeypatch.setattr(jobs, "encode_preview", flaky)
    result = jobs.separate_job(song)
    assert result["previews"] is False
    stemset = StemSet.model_validate_json(storage.get_bytes(song, "stems/stemset.json"))
    assert stemset.preview is None and all(s.preview is None for s in stemset.stems)
    assert storage.list_names(song, "stems/preview/") == []
    assert all(storage.exists(song, f"stems/{n}.wav") for n in STEM_NAMES)


@requires_ffmpeg
def test_stagepack_job_requires_stems_and_analysis(song: str, fake_models: None) -> None:
    with pytest.raises(jobs.JobError, match="run separation first"):
        jobs.stagepack_job(song, {"destination": "daw"})
    jobs.separate_job(song)
    with pytest.raises(jobs.JobError, match="run analysis first"):
        jobs.stagepack_job(song, {"destination": "daw"})


def test_stagepack_job_rejects_invalid_options(song: str, fake_models: None) -> None:
    with pytest.raises(jobs.JobError, match="invalid stagepack options"):
        jobs.stagepack_job(song, {"destination": "vinyl"})


@requires_ffmpeg
def test_full_pipeline_builds_equal_length_pack(
    song: str, storage: LocalStorage, fake_models: None, recorder: StageRecorder
) -> None:
    jobs.analyze_job(song, source_name="Mi Cancion.wav")
    jobs.separate_job(song, source_name="Mi Cancion.wav")
    recorder.stages.clear()
    name = jobs.stagepack_job(song, {"destination": "daw", "sample_rate": 48000})
    assert recorder.stages == ["loading", "packing", "saving", "done"]
    assert name.endswith(".zip")
    (stored,) = storage.list_names(song, "packs/")
    assert stored.startswith("packs/") and stored.endswith(f"/{name}")
    with zipfile.ZipFile(io.BytesIO(storage.get_bytes(song, stored))) as archive:
        wavs = [n for n in archive.namelist() if n.endswith(".wav")]
        frames = {sf.info(io.BytesIO(archive.read(n))).frames for n in wavs}
        assert len(wavs) >= len(STEM_NAMES) + 2
        assert len(frames) == 1
        assert "Secciones.txt" in archive.namelist()


@requires_ffmpeg
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
    assert storage.list_names(song, "packs/") == [f"packs/{pack.id}/{pack.return_value()}"]


@requires_ffmpeg
def test_two_packs_of_one_song_coexist(
    song: str, storage: LocalStorage, fake_models: None, queue
) -> None:
    queue.enqueue(jobs.analyze_job, song)
    queue.enqueue(jobs.separate_job, song)
    daw = queue.enqueue(jobs.stagepack_job, song, {"destination": "daw", "sample_rate": 48000})
    play = queue.enqueue(jobs.stagepack_job, song, {"destination": "playback"})

    assert daw.return_value() == play.return_value()  # same readable ZIP name
    stored = storage.list_names(song, "packs/")
    assert stored == sorted(
        [f"packs/{daw.id}/{daw.return_value()}", f"packs/{play.id}/{play.return_value()}"]
    )
    assert storage.get_bytes(song, stored[0]) != storage.get_bytes(song, stored[1])


def test_failed_job_is_recorded_by_the_queue(storage_root: Path, fake_models: None, queue) -> None:
    job = queue.enqueue(jobs.analyze_job, "ghost")
    assert job.get_status() == JobStatus.FAILED
    assert "song expired or deleted" in job.latest_result().exc_string


def test_source_selection_ignores_lookalikes(
    song: str, storage: LocalStorage, tmp_path: Path
) -> None:
    other = tmp_path / "x.bin"
    other.write_bytes(b"x")
    storage.put_file(song, "sourcefoo.wav", other)
    storage.put_file(song, "stems/source.wav", other)
    assert jobs._source_name(storage, song) == "source.wav"


def test_source_selection_rejects_ambiguity(
    song: str, storage: LocalStorage, tmp_path: Path, fake_models: None
) -> None:
    other = tmp_path / "x.bin"
    other.write_bytes(b"x")
    storage.put_file(song, "source.mp3", other)
    with pytest.raises(jobs.JobError, match="ambiguous source audio"):
        jobs.analyze_job(song)
    with pytest.raises(jobs.JobError, match="ambiguous source audio"):
        jobs.separate_job(song)


@requires_ffmpeg
def test_rerun_keeps_edited_sections_and_refreshes_detected(
    song: str, storage: LocalStorage, fake_models: None
) -> None:
    jobs.analyze_job(song)
    edited = Sections.model_validate_json(storage.get_bytes(song, "sections.json"))
    edited.sections[0].label = "edited by hand"
    storage.put_bytes(song, "sections.json", edited.model_dump_json().encode())
    storage.put_bytes(song, "sections.detected.json", b"stale")

    result = jobs.analyze_job(song)

    kept = Sections.model_validate_json(storage.get_bytes(song, "sections.json"))
    assert kept.sections[0].label == "edited by hand"
    detected = Sections.model_validate_json(storage.get_bytes(song, "sections.detected.json"))
    assert detected.sections[0].label != "edited by hand"
    assert result["sections_overwritten"] is False
    assert result["sections"] == "sections.json"
    assert result["sections_detected"] == "sections.detected.json"


@requires_ffmpeg
def test_overwrite_sections_replaces_the_editable_file(
    song: str, storage: LocalStorage, fake_models: None
) -> None:
    jobs.analyze_job(song)
    storage.put_bytes(song, "sections.json", b"user edit")
    result = jobs.analyze_job(song, overwrite_sections=True)
    assert storage.get_bytes(song, "sections.json") == storage.get_bytes(
        song, "sections.detected.json"
    )
    assert result["sections_overwritten"] is True


@requires_ffmpeg
def test_rerun_without_sections_touches_no_section_file(
    song: str, storage: LocalStorage, fake_models: None
) -> None:
    jobs.analyze_job(song)
    storage.put_bytes(song, "sections.json", b"user edit")
    result = jobs.analyze_job(song, sections=False)
    assert storage.get_bytes(song, "sections.json") == b"user edit"
    assert result["sections"] == "sections.json"
    assert result["sections_detected"] is None


@requires_ffmpeg
def test_detection_failure_changes_no_file(
    song: str, storage: LocalStorage, fake_models: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs.analyze_job(song)
    before = {n: storage.get_bytes(song, n) for n in storage.list_names(song)}

    def boom(*args, **kwargs):
        raise RuntimeError("detector crashed")

    monkeypatch.setattr(jobs, "detect_sections", boom)
    with pytest.raises(RuntimeError, match="detector crashed"):
        jobs.analyze_job(song, overwrite_sections=True)
    assert {n: storage.get_bytes(song, n) for n in storage.list_names(song)} == before


# --- job markers: lock while running, result marker once finished -----------------------------


class _JobStub:
    def __init__(self, job_id: str) -> None:
        self.id = job_id
        self.meta: dict = {}

    def save_meta(self) -> None:
        pass


def test_tracked_job_holds_a_lock_while_running_and_leaves_a_result_marker(
    storage: LocalStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "get_current_job", lambda: _JobStub("job-1"))
    storage.put_bytes("s1", "source.wav", b"x")
    seen = {}

    @jobs.tracked
    def work(song_id: str) -> dict:
        seen["lock"] = storage.exists(song_id, "jobs/job-1.lock")
        seen["marker_during"] = storage.exists(song_id, "jobs/job-1.json")
        return {"ok": True}

    assert work("s1") == {"ok": True}
    assert seen == {"lock": True, "marker_during": False}
    assert not storage.exists("s1", "jobs/job-1.lock")
    assert json.loads(storage.get_bytes("s1", "jobs/job-1.json")) == {"result": {"ok": True}}


def test_failed_job_releases_its_lock_and_writes_no_result(
    storage: LocalStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "get_current_job", lambda: _JobStub("job-2"))
    storage.put_bytes("s1", "source.wav", b"x")

    @jobs.tracked
    def work(song_id: str) -> None:
        raise jobs.JobError("boom")

    with pytest.raises(jobs.JobError):
        work("s1")
    assert storage.list_names("s1", "jobs/") == []


def test_job_for_a_song_the_sweep_deleted_fails_and_recreates_nothing(
    storage: LocalStorage, storage_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "get_current_job", lambda: _JobStub("job-gone"))
    ran = []

    @jobs.tracked
    def work(song_id: str) -> None:
        ran.append(song_id)

    with pytest.raises(jobs.JobError, match="song expired or deleted"):
        work("gone")
    assert ran == []
    assert not (storage_root / "gone").exists()


def test_string_results_are_recorded_verbatim(
    storage: LocalStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "get_current_job", lambda: _JobStub("job-3"))
    storage.put_bytes("s1", "source.wav", b"x")
    jobs.tracked(lambda song_id: "Pack A.zip")("s1")
    assert json.loads(storage.get_bytes("s1", "jobs/job-3.json")) == {"result": "Pack A.zip"}


def test_no_markers_outside_an_rq_job(storage: LocalStorage) -> None:
    jobs.tracked(lambda song_id: "x")("s1")
    assert storage.list_names("s1") == []


@requires_ffmpeg
def test_real_rq_job_writes_a_result_marker_named_after_its_id(
    song: str, storage: LocalStorage, fake_models: None, queue
) -> None:
    job = queue.enqueue(jobs.separate_job, song, job_id="job-real")
    assert job.get_status() == JobStatus.FINISHED
    marker = json.loads(storage.get_bytes(song, "jobs/job-real.json"))
    assert marker["result"]["song_id"] == song
    assert not storage.exists(song, "jobs/job-real.lock")


def test_stagepack_outside_rq_is_stored_under_a_recognisable_orphan_directory(
    song: str, storage: LocalStorage, fake_models: None, caplog
) -> None:
    jobs.analyze_job(song, source_name="Mi Cancion.wav")
    jobs.separate_job(song, source_name="Mi Cancion.wav")
    with caplog.at_level("WARNING"):
        name = jobs.stagepack_job(song, {"destination": "daw", "sample_rate": 48000})

    (stored,) = storage.list_names(song, "packs/")
    assert stored.startswith("packs/direct-") and stored.endswith(f"/{name}")
    assert "outside an RQ job" in caplog.text


def _long_wav(path: Path, seconds: int) -> None:
    sf.write(str(path), np.zeros(seconds * 8000, dtype=np.float32), 8000)


@requires_ffmpeg
@pytest.mark.parametrize("job", [jobs.analyze_job, jobs.separate_job])
def test_jobs_reject_a_song_over_the_maximum_before_decoding(
    job, storage: LocalStorage, tmp_path: Path, fake_models: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    wav = tmp_path / "long.wav"
    _long_wav(wav, 601 + 1)  # 602 s mono at 8 kHz is about 10 MB
    storage.put_file("long", "source.wav", wav)

    def no_decode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("decode must not run for an over-long file")

    monkeypatch.setattr(jobs, "decode", no_decode)
    with pytest.raises(jobs.JobError, match=r"El tema dura 10:02 y el máximo es 10:00\."):
        job("long")


def test_over_long_message_is_in_minutes_and_seconds() -> None:
    with pytest.raises(jobs.JobError, match=r"23:41 y el máximo es 10:00"):
        jobs._check_duration(23 * 60 + 41.4)
    jobs._check_duration(600.5)  # tolerance
    jobs._check_duration(600)


def test_decoded_length_decides_when_ffprobe_fails(
    song: str, storage: LocalStorage, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    long_audio = np.zeros((2, 620 * SAMPLE_RATE // 10), dtype=np.float32)  # 62 s of audio
    monkeypatch.setattr(jobs, "probe_duration", lambda _p: None)
    monkeypatch.setattr(jobs, "decode", lambda _p: long_audio)
    monkeypatch.setattr(jobs, "MAX_DURATION_SECONDS", 60)
    with pytest.raises(jobs.JobError, match="El tema dura 1:02 y el máximo es 1:00"):
        jobs.analyze_job(song)
