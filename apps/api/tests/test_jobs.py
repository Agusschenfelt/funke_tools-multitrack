import pytest
from audio_core.models import Analysis

from api.models import Pack
from api.queueing import QueueUnavailable, RemoteJob, map_status


def put_analysis_and_stems(store, song_id, duration=12.5):
    analysis = Analysis(
        source="x",
        duration=duration,
        sample_rate=44100,
        grid=None,
        key=None,
        loudness=None,
        models={},
    )
    store.put_bytes(song_id, "analysis.json", analysis.model_dump_json().encode())
    store.put_bytes(song_id, "stems/stemset.json", b"{}")
    store.put_bytes(song_id, "stems/drums.wav", b"wav")


def test_analyze_enqueues_by_dotted_path_with_source_name(client, queue, song):
    response = client.post(f"/songs/{song['id']}/analyze")

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    [call] = queue.enqueued
    assert call["func"] == "worker_cpu.jobs.analyze_job"
    assert call["args"] == (song["id"],)
    assert call["kwargs"] == {"sections": True, "source_name": "Song One.wav"}
    assert call["job_id"] == job_id
    assert call["timeout"] > 180


def test_analyze_without_sections(client, queue, song):
    client.post(f"/songs/{song['id']}/analyze", json={"sections": False})
    assert queue.enqueued[0]["kwargs"]["sections"] is False


def test_separate_enqueues_model(client, queue, song):
    response = client.post(f"/songs/{song['id']}/separate", json={"model": "htdemucs_ft"})

    assert response.status_code == 202
    [call] = queue.enqueued
    assert call["func"] == "worker_cpu.jobs.separate_job"
    assert call["args"] == (song["id"],)
    assert call["kwargs"] == {"model": "htdemucs_ft", "source_name": "Song One.wav"}


def test_separate_defaults_to_htdemucs_6s(client, queue, song):
    client.post(f"/songs/{song['id']}/separate")
    assert queue.enqueued[0]["kwargs"]["model"] == "htdemucs_6s"


def test_separate_rejects_unknown_model(client, queue, song):
    response = client.post(f"/songs/{song['id']}/separate", json={"model": "mdx_extra"})
    assert response.status_code == 422
    assert queue.enqueued == []


def test_stagepack_requires_analysis_and_stems(client, queue, store, song):
    sid = song["id"]
    body = {"destination": "daw"}

    missing = client.post(f"/songs/{sid}/stagepack", json=body)
    assert missing.status_code == 409
    assert "analysis" in missing.json()["detail"] and "stems" in missing.json()["detail"]

    store.put_bytes(sid, "analysis.json", b"{}")
    only_analysis = client.post(f"/songs/{sid}/stagepack", json=body)
    assert only_analysis.status_code == 409
    assert "stems" in only_analysis.json()["detail"]
    assert queue.enqueued == []


def test_stagepack_enqueues_options(client, queue, store, song):
    put_analysis_and_stems(store, song["id"])
    response = client.post(
        f"/songs/{song['id']}/stagepack",
        json={"destination": "playback", "count_in_bars": 2, "click_sound": "cowbell"},
    )

    assert response.status_code == 202
    [call] = queue.enqueued
    assert call["func"] == "worker_cpu.jobs.stagepack_job"
    assert call["args"][0] == song["id"]
    options = call["args"][1]
    assert options["destination"] == "playback"
    assert options["count_in_bars"] == 2
    assert options["click_sound"] == "cowbell"
    assert options["language"] == "es"
    assert call["kwargs"] == {}


def test_stagepack_validates_options(client, queue, store, song):
    put_analysis_and_stems(store, song["id"])
    bad = client.post(f"/songs/{song['id']}/stagepack", json={"destination": "prime"})
    assert bad.status_code == 422
    assert queue.enqueued == []


def test_queue_down_returns_503_and_leaves_no_job(client, queue, song):
    queue.fail_enqueue = QueueUnavailable("redis down")
    response = client.post(f"/songs/{song['id']}/analyze")

    assert response.status_code == 503
    queue.fail_enqueue = None
    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    assert client.get(f"/jobs/{job_id}").status_code == 200


@pytest.mark.parametrize(
    ("rq_status", "expected"),
    [
        ("queued", "queued"),
        ("deferred", "queued"),
        ("scheduled", "queued"),
        ("started", "running"),
        ("finished", "finished"),
        ("failed", "failed"),
        ("stopped", "failed"),
        ("canceled", "failed"),
        (None, "queued"),
    ],
)
def test_status_mapping(rq_status, expected):
    assert map_status(rq_status) == expected


def test_job_status_before_worker_picks_it_up(client, queue, song):
    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    body = client.get(f"/jobs/{job_id}").json()

    assert body["job_id"] == job_id
    assert body["song_id"] == song["id"]
    assert body["kind"] == "analyze"
    assert body["status"] == "queued"
    assert body["stage"] is None
    assert body["download_url"] is None


def test_job_running_reports_stage_from_rq_meta(client, queue, clock, song):
    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    queue.remote[job_id] = RemoteJob(status="started", stage="analyzing")
    body = client.get(f"/jobs/{job_id}").json()

    assert body["status"] == "running"
    assert body["stage"] == "analyzing"
    assert body["started_at"] is not None
    assert body["finished_at"] is None


def test_job_failure_surfaces_error_line(client, queue, song):
    job_id = client.post(f"/songs/{song['id']}/separate").json()["job_id"]
    queue.remote[job_id] = RemoteJob(
        status="failed", stage="separating", error="JobError: no source audio"
    )
    body = client.get(f"/jobs/{job_id}").json()

    assert body["status"] == "failed"
    assert body["error"] == "JobError: no source audio"
    assert body["finished_at"] is not None


def test_finished_analyze_records_result_and_duration(client, queue, store, song):
    put_analysis_and_stems(store, song["id"], duration=210.5)
    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    queue.remote[job_id] = RemoteJob(
        status="finished", stage="done", result={"song_id": song["id"], "bpm": 120.0}
    )
    body = client.get(f"/jobs/{job_id}").json()

    assert body["status"] == "finished"
    assert body["result"]["bpm"] == 120.0
    assert client.get(f"/songs/{song['id']}").json()["duration"] == 210.5


def test_finished_job_is_terminal_and_survives_rq_expiry(client, queue, song):
    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    queue.remote[job_id] = RemoteJob(status="finished", stage="done", result={"bpm": 90})
    client.get(f"/jobs/{job_id}")
    queue.remote.clear()  # RQ forgot the job
    body = client.get(f"/jobs/{job_id}").json()

    assert body["status"] == "finished"
    assert body["result"] == {"bpm": 90}


def test_finished_stagepack_returns_filename_and_working_download(client, queue, store, song):
    sid = song["id"]
    put_analysis_and_stems(store, sid)
    job_id = client.post(f"/songs/{sid}/stagepack", json={"destination": "daw"}).json()["job_id"]
    store.put_bytes(sid, "packs/Song One - DAW.zip", b"PK-zip-bytes")
    queue.remote[job_id] = RemoteJob(status="finished", stage="done", result="Song One - DAW.zip")

    body = client.get(f"/jobs/{job_id}").json()
    assert body["status"] == "finished"
    assert body["result"] == {"filename": "Song One - DAW.zip"}
    assert body["download_url"].startswith("/files/")

    download = client.get(body["download_url"])
    assert download.status_code == 200
    assert download.content == b"PK-zip-bytes"
    assert "Song%20One%20-%20DAW.zip" in download.headers["content-disposition"]

    with client.app.state.ctx.session_factory() as session:
        pack = session.query(Pack).one()
    assert pack.filename == "Song One - DAW.zip"
    assert pack.job_id == job_id
    assert pack.options["destination"] == "daw"


def test_unknown_job_is_404(client):
    assert client.get("/jobs/does-not-exist").status_code == 404


def test_job_of_expired_song_is_404(client, queue, clock, song):
    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    clock.advance(hours=25)
    assert client.get(f"/jobs/{job_id}").status_code == 404


def test_job_row_ids_match_rq_ids(client, queue, song):
    ids = {client.post(f"/songs/{song['id']}/analyze").json()["job_id"] for _ in range(3)}
    assert ids == {c["job_id"] for c in queue.enqueued}
    assert len(ids) == 3
