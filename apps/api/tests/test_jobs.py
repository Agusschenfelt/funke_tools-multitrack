import json

import pytest
from audio_core.models import Analysis
from conftest import SECRET

from api.models import Job, Pack
from api.queueing import QueueUnavailable, RemoteJob, map_status
from api.services import ENQUEUE_FAILED_ERROR


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


def test_queue_down_returns_503_and_keeps_a_failed_job(client, queue, song):
    queue.fail_enqueue = QueueUnavailable("redis down")
    response = client.post(f"/songs/{song['id']}/analyze")

    assert response.status_code == 503
    with client.app.state.ctx.session_factory() as session:
        (row,) = session.query(Job).all()
        assert row.status == "failed"
        assert "enqueue failed" in row.error
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
    store.put_bytes(sid, f"packs/{job_id}/Song One - DAW.zip", b"PK-zip-bytes")
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


def test_two_packs_of_one_song_keep_their_own_files_and_links(client, queue, store, song):
    """Same readable ZIP name, different options: neither pack overwrites or serves the other."""
    sid = song["id"]
    put_analysis_and_stems(store, sid)
    first = stagepack(client, sid, destination="daw")
    second = stagepack(client, sid, destination="playback")
    store.put_bytes(sid, f"packs/{first}/Song - C - 90 BPM.zip", b"first-pack")
    store.put_bytes(sid, f"packs/{second}/Song - C - 90 BPM.zip", b"second-pack")
    for job_id in (first, second):
        queue.remote[job_id] = RemoteJob(
            status="finished", stage="done", result="Song - C - 90 BPM.zip"
        )

    urls = [client.get(f"/jobs/{j}").json()["download_url"] for j in (first, second)]
    assert urls[0] != urls[1]
    bodies = [client.get(u) for u in urls]
    assert [r.content for r in bodies] == [b"first-pack", b"second-pack"]
    assert all(
        "Song%20-%20C%20-%2090%20BPM.zip" in r.headers["content-disposition"] for r in bodies
    )

    packs = client.get(f"/songs/{sid}").json()["artifacts"]["packs"]
    assert [p["name"] for p in packs] == ["Song - C - 90 BPM.zip"] * 2
    assert sorted(client.get(p["url"]).content for p in packs) == [b"first-pack", b"second-pack"]


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


# --- lost jobs, RQ datetimes and enqueue ordering -------------------------------------------


def test_lost_job_within_grace_stays_queued(client, queue, clock, settings, song):
    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    clock.advance(seconds=settings.lost_job_grace_seconds - 1)
    body = client.get(f"/jobs/{job_id}").json()  # RQ has no record yet

    assert body["status"] == "queued"
    assert body["error"] is None


def test_lost_job_is_failed_after_grace(client, queue, clock, settings, song):
    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    clock.advance(seconds=settings.lost_job_grace_seconds)
    body = client.get(f"/jobs/{job_id}").json()

    assert body["status"] == "failed"
    assert "job lost" in body["error"]
    assert body["finished_at"] is not None
    # Terminal rows are immutable: a later reappearance in RQ does not resurrect it.
    queue.remote[job_id] = RemoteJob(status="started")
    assert client.get(f"/jobs/{job_id}").json()["status"] == "failed"


def write_marker(store, song_id, job_id, result):
    """What the worker's ``tracked`` wrapper leaves behind for a successful job."""
    store.put_bytes(song_id, f"jobs/{job_id}.json", json.dumps({"result": result}).encode())


def test_expired_rq_entry_with_result_marker_is_finished_not_lost(
    client, queue, store, clock, settings, song
):
    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    store.put_bytes(song["id"], "analysis.json", b'{"duration": 12.5}')
    write_marker(store, song["id"], job_id, {"bpm": 120.0})
    clock.advance(seconds=settings.lost_job_grace_seconds)
    body = client.get(f"/jobs/{job_id}").json()  # RQ forgot the job before anyone polled

    assert body["status"] == "finished"
    assert body["error"] is None
    assert body["result"] == {"bpm": 120.0}
    assert body["finished_at"] is not None
    assert client.get(f"/songs/{song['id']}").json()["duration"] == 12.5


def test_expired_rq_entry_with_marker_separate_is_finished(
    client, queue, store, clock, settings, song
):
    job_id = client.post(f"/songs/{song['id']}/separate").json()["job_id"]
    write_marker(store, song["id"], job_id, {"stems": ["drums"]})
    clock.advance(seconds=settings.lost_job_grace_seconds)

    assert client.get(f"/jobs/{job_id}").json()["status"] == "finished"


def stagepack(client, sid, destination="daw"):
    return client.post(f"/songs/{sid}/stagepack", json={"destination": destination}).json()[
        "job_id"
    ]


def test_expired_rq_entry_stagepack_records_the_pack_named_by_its_marker(
    client, queue, store, clock, settings, song
):
    put_analysis_and_stems(store, song["id"])
    job_id = stagepack(client, song["id"])
    store.put_bytes(song["id"], f"packs/{job_id}/Song One-daw.zip", b"zip")
    write_marker(store, song["id"], job_id, "Song One-daw.zip")
    clock.advance(seconds=settings.lost_job_grace_seconds)
    body = client.get(f"/jobs/{job_id}").json()

    assert body["status"] == "finished"
    assert body["result"] == {"filename": "Song One-daw.zip"}
    with client.app.state.ctx.session_factory() as session:
        assert session.query(Pack).one().filename == "Song One-daw.zip"


def test_lost_stagepack_never_adopts_another_jobs_pack(client, queue, store, clock, settings, song):
    """Two packs on the song: the lost job has no marker, so it must not claim either of them."""
    put_analysis_and_stems(store, song["id"])
    done = stagepack(client, song["id"])
    lost = stagepack(client, song["id"], destination="playback")
    store.put_bytes(song["id"], f"packs/{done}/Pack B.zip", b"zip-b")
    write_marker(store, song["id"], done, "Pack B.zip")
    clock.advance(seconds=settings.lost_job_grace_seconds)

    assert client.get(f"/jobs/{lost}").json()["status"] == "failed"
    ok = client.get(f"/jobs/{done}").json()
    assert ok["status"] == "finished"
    assert ok["result"] == {"filename": "Pack B.zip"}
    with client.app.state.ctx.session_factory() as session:
        names = {p.job_id: p.filename for p in session.query(Pack)}
    assert names == {done: "Pack B.zip", lost: None}


def test_rerun_whose_old_artifact_exists_is_not_mistaken_for_finished(
    client, queue, store, clock, settings, song
):
    """The first analysis left analysis.json; a lost re-run has its own (absent) marker."""
    first = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    store.put_bytes(song["id"], "analysis.json", b"{}")
    write_marker(store, song["id"], first, {"bpm": 100})
    rerun = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    clock.advance(seconds=settings.lost_job_grace_seconds)

    assert client.get(f"/jobs/{rerun}").json()["status"] == "failed"
    assert client.get(f"/jobs/{first}").json()["status"] == "finished"


def test_unreadable_marker_counts_as_lost(client, queue, store, clock, settings, song):
    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    store.put_bytes(song["id"], f"jobs/{job_id}.json", b"{not json")
    clock.advance(seconds=settings.lost_job_grace_seconds)

    assert client.get(f"/jobs/{job_id}").json()["status"] == "failed"


def test_storage_error_while_reading_the_marker_leaves_the_job_undecided(
    client, queue, store, clock, settings, song, monkeypatch
):
    from api.storage import StorageError

    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    clock.advance(seconds=settings.lost_job_grace_seconds)

    def broken(*args, **kwargs):
        raise StorageError("disk hiccup")

    monkeypatch.setattr(type(store), "exists", broken)
    assert client.get(f"/jobs/{job_id}").json()["status"] == "queued"


def test_expired_rq_entry_without_marker_is_still_lost(client, queue, clock, settings, song):
    job_id = client.post(f"/songs/{song['id']}/separate").json()["job_id"]
    clock.advance(seconds=settings.lost_job_grace_seconds)

    body = client.get(f"/jobs/{job_id}").json()
    assert body["status"] == "failed"
    assert "job lost" in body["error"]


def test_rq_records_are_kept_for_twice_the_song_life_and_enqueue_uses_it(monkeypatch):
    """The TTL handed to RQ is derived from the song TTL setting, not a separate constant."""
    from rq import Queue

    from api.config import Settings
    from api.queueing import RqQueue

    settings = Settings(signing_secret=SECRET, song_ttl_hours=5)
    assert settings.result_ttl_seconds == 2 * 5 * 3600

    seen = {}

    def fake_enqueue(self, func, **kwargs):
        seen.update(kwargs)

    monkeypatch.setattr(Queue, "enqueue", fake_enqueue)
    queue = RqQueue("redis://unused", settings.result_ttl_seconds)
    queue._connection = object()
    queue.enqueue("worker_cpu.jobs.analyze_job", ("s",), {}, job_id="j", timeout=10)

    assert seen["result_ttl"] == seen["failure_ttl"] == 2 * 5 * 3600
    assert seen["result_ttl"] > settings.song_ttl_hours * 3600  # outlives the song it belongs to


def test_rq_queue_serializes_job_records_as_json(monkeypatch):
    from rq import Queue
    from rq.serializers import JSONSerializer

    from api.queueing import RqQueue

    seen = {}
    original_init = Queue.__init__

    def spy_init(self, *args, **kwargs):
        seen["serializer"] = kwargs.get("serializer")
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(Queue, "__init__", spy_init)
    monkeypatch.setattr(Queue, "enqueue", lambda self, func, **kw: None)
    queue = RqQueue("redis://unused", 10)
    queue._connection = object()
    queue.enqueue("worker_cpu.jobs.analyze_job", ("s",), {}, job_id="j", timeout=10)

    assert seen["serializer"] is JSONSerializer


def test_running_job_the_queue_forgot_is_also_failed(client, queue, clock, settings, song):
    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    queue.remote[job_id] = RemoteJob(status="started", stage="analyzing")
    assert client.get(f"/jobs/{job_id}").json()["status"] == "running"
    queue.remote.clear()
    clock.advance(seconds=settings.lost_job_grace_seconds + 1)

    assert client.get(f"/jobs/{job_id}").json()["status"] == "failed"


def test_queue_outage_does_not_fail_the_job(client, queue, clock, settings, song):
    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    clock.advance(hours=1)

    def down(_job_id):
        raise QueueUnavailable("redis down")

    queue.fetch = down
    assert client.get(f"/jobs/{job_id}").json()["status"] == "queued"


def test_aware_utc_converts_naive_and_keeps_aware():
    from datetime import UTC, datetime, timedelta, timezone

    from api.queueing import aware_utc

    assert aware_utc(None) is None
    naive = datetime(2026, 10, 26, 12, 0)
    assert aware_utc(naive) == datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    plus_two = datetime(2026, 10, 26, 14, 0, tzinfo=timezone(timedelta(hours=2)))
    converted = aware_utc(plus_two)
    assert converted == datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    assert converted.utcoffset() == timedelta(0)


class StubRqJob:
    """Shape of ``rq.job.Job`` as read by ``RqQueue.fetch`` (RQ datetimes are naive UTC)."""

    meta = {"stage": "analyzing"}
    is_failed = False
    is_finished = True
    result = {"bpm": 100}

    def __init__(self):
        from datetime import datetime

        self.started_at = datetime(2026, 10, 26, 12, 0, 5)
        self.ended_at = datetime(2026, 10, 26, 12, 3, 0)

    def get_status(self, refresh=True):
        return "finished"

    def latest_result(self):
        return None


def test_rq_queue_fetch_returns_aware_utc_datetimes(monkeypatch):
    from datetime import UTC, datetime

    from rq.job import Job

    from api.queueing import RqQueue

    monkeypatch.setattr(
        Job, "fetch", staticmethod(lambda job_id, connection, serializer=None: StubRqJob())
    )
    queue = RqQueue("redis://unused", 10)
    queue._connection = object()
    remote = queue.fetch("x")

    assert remote.started_at == datetime(2026, 10, 26, 12, 0, 5, tzinfo=UTC)
    assert remote.ended_at.tzinfo is not None
    assert remote.result == {"bpm": 100}


def test_rq_queue_fetch_maps_the_real_jobstatus_enum(monkeypatch):
    from rq.job import Job, JobStatus

    from api.queueing import RqQueue, map_status

    class EnumStatusJob(StubRqJob):
        def get_status(self, refresh=True):
            return JobStatus.FINISHED

    monkeypatch.setattr(
        Job, "fetch", staticmethod(lambda job_id, connection, serializer=None: EnumStatusJob())
    )
    queue = RqQueue("redis://unused", 10)
    queue._connection = object()
    remote = queue.fetch("x")

    assert remote.status == "finished"
    assert map_status(remote.status) == "finished"


def test_rq_queue_fetch_distinguishes_missing_from_outage(monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError
    from rq.exceptions import NoSuchJobError
    from rq.job import Job

    from api.queueing import RqQueue

    queue = RqQueue("redis://unused", 10)
    queue._connection = object()

    def missing(job_id, connection, serializer=None):
        raise NoSuchJobError(job_id)

    monkeypatch.setattr(Job, "fetch", staticmethod(missing))
    assert queue.fetch("x") is None

    def down(job_id, connection, serializer=None):
        raise RedisConnectionError("refused")

    monkeypatch.setattr(Job, "fetch", staticmethod(down))
    with pytest.raises(QueueUnavailable):
        queue.fetch("x")


def test_finished_job_with_aware_rq_times_is_stored(client, queue, song):
    """End to end: RqQueue-style aware datetimes bind to the UTC column without error."""
    from datetime import UTC, datetime

    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]
    queue.remote[job_id] = RemoteJob(
        status="finished",
        stage="done",
        result={"bpm": 1},
        started_at=datetime(2026, 10, 26, 12, 0, 5, tzinfo=UTC),
        ended_at=datetime(2026, 10, 26, 12, 3, tzinfo=UTC),
    )
    body = client.get(f"/jobs/{job_id}").json()
    assert body["finished_at"].startswith("2026-10-26T12:03:00")


def test_job_row_is_committed_before_enqueue(client, queue, song):
    seen = {}
    original = queue.enqueue

    def checking_enqueue(func, args, kwargs, *, job_id, timeout):
        # A separate session only sees committed rows (a worker would).
        with client.app.state.ctx.session_factory() as other:
            seen["row"] = other.get(Job, job_id)
        original(func, args, kwargs, job_id=job_id, timeout=timeout)

    queue.enqueue = checking_enqueue
    job_id = client.post(f"/songs/{song['id']}/analyze").json()["job_id"]

    assert seen["row"] is not None
    assert seen["row"].id == job_id
    assert seen["row"].status == "queued"


def test_failed_enqueue_keeps_the_job_failed_and_drops_its_orphan_pack(client, queue, store, song):
    put_analysis_and_stems(store, song["id"])
    queue.fail_enqueue = QueueUnavailable("redis down")
    response = client.post(f"/songs/{song['id']}/stagepack", json={"destination": "daw"})

    assert response.status_code == 503
    with client.app.state.ctx.session_factory() as session:
        (job,) = session.query(Job).all()
        assert job.status == "failed"
        assert job.error == ENQUEUE_FAILED_ERROR
        assert session.query(Pack).count() == 0  # the pack of a failed job can never be filled


def test_reanalysis_never_asks_the_worker_to_overwrite_edited_sections(client, queue, store, song):
    sid = song["id"]
    edit = {"sections": [{"name": "intro", "start": 0.0}, {"name": "verse", "start": 8.0}]}
    assert client.put(f"/songs/{sid}/sections", json=edit).status_code == 200
    client.post(f"/songs/{sid}/analyze")

    kwargs = queue.enqueued[-1]["kwargs"]
    assert "overwrite_sections" not in kwargs
    sections = client.get(f"/songs/{sid}/sections").json()
    assert sections["edited"] is True
    assert [s["name"] for s in sections["sections"]] == ["intro", "verse"]
