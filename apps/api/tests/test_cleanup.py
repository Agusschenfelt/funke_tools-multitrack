import asyncio

import pytest
from conftest import SECRET, upload
from fastapi.testclient import TestClient

from api.cleanup import INFLIGHT_MARGIN, cleanup_expired, cleanup_loop, sweep_expired
from api.config import ConfigError, Settings
from api.main import create_app
from api.models import Job, Pack, SectionsState, Song


def count(client, model) -> int:
    with client.app.state.ctx.session_factory() as session:
        return session.query(model).count()


def populate(client, queue, store, content: bytes, name: str) -> dict:
    """A song with a job, a pack row, an edited-sections state and stored files."""
    song = upload(client, content, name).json()
    sid = song["id"]
    store.put_bytes(sid, "analysis.json", b"{}")
    store.put_bytes(sid, "stems/stemset.json", b"{}")
    store.put_bytes(sid, "stems/drums.wav", b"wav")
    sections = {"sections": [{"name": "intro", "start": 0.0}]}
    assert client.put(f"/songs/{sid}/sections", json=sections).status_code == 200
    client.post(f"/songs/{sid}/analyze")
    client.post(f"/songs/{sid}/stagepack", json={"destination": "daw"})
    with client.app.state.ctx.session_factory() as session:  # settled jobs do not defer cleanup
        for job in session.query(Job).filter(Job.song_id == sid):
            job.status = "finished"
        session.commit()
    return song


def test_cleanup_deletes_expired_songs_rows_and_files(client, queue, store, clock):
    old = populate(client, queue, store, b"old-bytes", "old.wav")
    clock.advance(hours=23)
    fresh = populate(client, queue, store, b"fresh-bytes", "fresh.wav")
    clock.advance(hours=1, seconds=1)  # old is now 24 h + 1 s, fresh is 1 h + 1 s

    deleted = cleanup_expired(client.app.state.ctx)

    assert deleted == [old["id"]]
    assert store.list_names(old["id"]) == []
    assert not (store.root / old["id"]).exists()
    assert store.list_names(fresh["id"]) != []
    with client.app.state.ctx.session_factory() as session:
        assert [s.id for s in session.query(Song)] == [fresh["id"]]
        assert {j.song_id for j in session.query(Job)} == {fresh["id"]}
        assert {p.song_id for p in session.query(Pack)} == {fresh["id"]}
        assert {s.song_id for s in session.query(SectionsState)} == {fresh["id"]}
    assert client.get(f"/songs/{fresh['id']}").status_code == 200


def test_cleanup_boundary_is_exactly_24_hours(client, store, clock):
    song = upload(client, b"edge", "e.wav").json()
    clock.advance(hours=24, seconds=-1)
    assert cleanup_expired(client.app.state.ctx) == []
    clock.advance(seconds=1)
    assert cleanup_expired(client.app.state.ctx) == [song["id"]]


class FlakyStorage:
    """Delegates to the real storage but raises for the configured song ids."""

    def __init__(self, inner, bad: set[str]) -> None:
        self.inner = inner
        self.bad = bad

    def delete_song(self, song_id: str) -> None:
        if song_id in self.bad:
            raise OSError("disk error")
        self.inner.delete_song(song_id)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def test_one_failing_song_does_not_abort_the_sweep_and_is_retried(client, store, clock):
    ctx = client.app.state.ctx
    first = upload(client, b"one", "1.wav").json()["id"]
    second = upload(client, b"two", "2.wav").json()["id"]
    third = upload(client, b"three", "3.wav").json()["id"]
    clock.advance(hours=25)
    ctx.storage = FlakyStorage(store, {second})

    report = sweep_expired(ctx)

    assert sorted(report.deleted) == sorted([first, third])
    assert report.failed == [second]
    with ctx.session_factory() as session:
        assert [s.id for s in session.query(Song)] == [second]  # row kept for the retry

    ctx.storage = store  # the storage recovers
    retry = sweep_expired(ctx)
    assert retry.deleted == [second]
    assert retry.failed == []
    assert count(client, Song) == 0


def test_song_with_running_job_is_deferred_until_past_the_margin(client, store, clock):
    song = upload(client, b"busy", "b.wav").json()
    client.post(f"/songs/{song['id']}/analyze")  # stays queued
    ctx = client.app.state.ctx
    clock.advance(hours=24, seconds=1)

    report = sweep_expired(ctx)
    assert report.skipped_in_flight == [song["id"]]
    assert report.deleted == []
    assert count(client, Song) == 1

    clock.advance(seconds=INFLIGHT_MARGIN.total_seconds())
    assert sweep_expired(ctx).deleted == [song["id"]]


def test_cleanup_is_idempotent_and_empty_is_a_no_op(client, store, clock):
    assert cleanup_expired(client.app.state.ctx) == []
    upload(client, b"x", "x.wav")
    clock.advance(hours=25)
    assert len(cleanup_expired(client.app.state.ctx)) == 1
    assert cleanup_expired(client.app.state.ctx) == []
    assert count(client, Song) == 0


def test_cleanup_tolerates_already_missing_files(client, store, clock):
    song = upload(client, b"x", "x.wav").json()
    store.delete_song(song["id"])
    clock.advance(hours=25)
    assert cleanup_expired(client.app.state.ctx) == [song["id"]]
    assert count(client, Song) == 0


def test_expired_song_download_links_are_gone_after_cleanup(client, store, clock):
    song = upload(client, b"x", "x.wav").json()
    store.put_bytes(song["id"], "stems/drums.wav", b"wav")
    url = client.get(f"/songs/{song['id']}").json()["artifacts"]["stems"][0]["url"]
    clock.advance(hours=25)
    cleanup_expired(client.app.state.ctx)
    assert client.get(url).status_code in (410, 403)


# --- reuse ---------------------------------------------------------------------------------


def test_reuse_shows_existing_analysis_and_stems_in_song_detail(client, queue, store, clock):
    first = populate(client, queue, store, b"same-audio", "a.wav")
    clock.advance(hours=12)

    again = upload(client, b"same-audio", "renamed.wav")
    assert again.status_code == 200
    assert again.json()["reused"] is True
    assert again.json()["id"] == first["id"]

    artifacts = client.get(f"/songs/{again.json()['id']}").json()["artifacts"]
    assert artifacts["analysis"] is True
    assert artifacts["sections"] is True
    assert artifacts["sections_edited"] is True
    assert [s["name"] for s in artifacts["stems"]] == ["drums.wav"]
    assert len(queue.enqueued) == 2  # reuse enqueued nothing new


def test_after_expiry_same_hash_creates_a_fresh_song_without_old_artifacts(
    client, queue, store, clock
):
    first = populate(client, queue, store, b"same-audio", "a.wav")
    clock.advance(hours=24, seconds=1)
    cleanup_expired(client.app.state.ctx)

    second = upload(client, b"same-audio", "a.wav")

    assert second.status_code == 201
    assert second.json()["reused"] is False
    assert second.json()["id"] != first["id"]
    assert client.get(f"/songs/{first['id']}").status_code == 404
    artifacts = client.get(f"/songs/{second.json()['id']}").json()["artifacts"]
    assert artifacts["analysis"] is False
    assert artifacts["stems"] == []
    assert artifacts["sections_edited"] is False


def test_new_song_gets_a_fresh_24_hour_window(client, clock):
    upload(client, b"same", "a.wav")
    clock.advance(hours=24, seconds=1)
    second = upload(client, b"same", "a.wav").json()
    clock.advance(hours=23)
    assert client.get(f"/songs/{second['id']}").status_code == 200


# --- periodic task ---------------------------------------------------------------------------


def test_cleanup_loop_sweeps_then_sleeps_and_survives_errors(client, store, clock, monkeypatch):
    ctx = client.app.state.ctx
    upload(client, b"x", "x.wav")
    clock.advance(hours=25)
    calls = []

    async def fake_sleep(seconds):
        calls.append(seconds)
        if len(calls) == 3:
            raise asyncio.CancelledError

    real = sweep_expired
    attempts = []

    def flaky(c):
        attempts.append(1)
        if len(attempts) == 2:
            raise RuntimeError("database blip")
        return real(c)

    monkeypatch.setattr("api.cleanup.sweep_expired", flaky)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cleanup_loop(ctx, 900, sleep=fake_sleep))

    assert calls == [900, 900, 900]
    assert len(attempts) == 3  # the failing sweep did not stop the schedule
    assert count(client, Song) == 0


def test_lifespan_runs_cleanup_task_only_when_enabled(settings, queue, clock):
    from alembic import command
    from conftest import SECRET, alembic_config

    command.upgrade(alembic_config(settings.database_url), "head")
    with TestClient(create_app(settings, queue=queue, clock=clock)) as disabled:
        assert disabled.app.state.cleanup_task is None

    enabled_settings = Settings(
        signing_secret=SECRET,
        database_url=settings.database_url,
        storage_root=settings.storage_root,
        cleanup_interval_seconds=900,
    )
    app = create_app(enabled_settings, queue=queue, clock=clock)
    with TestClient(app):
        task = app.state.cleanup_task
        assert task is not None and not task.done()
    assert task.cancelled() or task.done()


def test_cleanup_interval_setting():
    assert Settings.from_env({"SIGNING_SECRET": SECRET}).cleanup_interval_seconds == 900
    off = Settings.from_env({"SIGNING_SECRET": SECRET, "CLEANUP_INTERVAL_SECONDS": "0"})
    assert off.cleanup_interval_seconds == 0
    assert Settings(signing_secret="s").cleanup_interval_seconds == 0
    with pytest.raises(ConfigError):
        Settings.from_env({"SIGNING_SECRET": SECRET, "CLEANUP_INTERVAL_SECONDS": "-1"})
    with pytest.raises(ConfigError):
        Settings.from_env({"SIGNING_SECRET": SECRET, "CLEANUP_INTERVAL_SECONDS": "soon"})


def test_cli_main_cleans_with_env_settings(client, store, clock, settings, monkeypatch, capsys):
    from api import cleanup as cleanup_module
    from api import main as main_module

    song = upload(client, b"x", "x.wav").json()
    clock.advance(hours=25)
    monkeypatch.setenv("SIGNING_SECRET", SECRET)
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    monkeypatch.setenv("STORAGE_ROOT", str(settings.storage_root))
    monkeypatch.setattr(main_module, "utc_now", lambda: clock())
    cleanup_module.main()

    out = capsys.readouterr().out
    assert "deleted 1 expired song(s)" in out
    assert song["id"] in out
    assert count(client, Song) == 0


def remove_everywhere(ctx, store, song_id: str) -> None:
    """What a concurrent sweep does: rows and files of one song, in its own session."""
    store.delete_song(song_id)
    with ctx.session_factory() as other:
        other.query(Job).filter(Job.song_id == song_id).delete()
        other.query(SectionsState).filter(SectionsState.song_id == song_id).delete()
        other.query(Song).filter(Song.id == song_id).delete()
        other.commit()


def test_song_deleted_by_a_concurrent_sweep_before_its_turn_does_not_abort(client, store, clock):
    ctx = client.app.state.ctx
    ids = [upload(client, bytes([i]) * 8, f"{i}.wav").json()["id"] for i in range(3)]
    clock.advance(hours=25)
    victim: str | None = None

    class Racing:
        def __init__(self, inner) -> None:
            self.inner = inner
            self.raced = False
            self.seen: set[str] = set()

        def delete_song(self, song_id: str) -> None:
            nonlocal victim
            if not self.raced:
                # Whatever order the sweep visits songs in, remove a song it has not reached yet.
                self.raced = True
                victim = next(i for i in ids if i != song_id and i not in self.seen)
                remove_everywhere(ctx, self.inner, victim)
            self.seen.add(song_id)
            self.inner.delete_song(song_id)

        def __getattr__(self, name):
            return getattr(self.inner, name)

    ctx.storage = Racing(store)
    report = sweep_expired(ctx)

    assert report.failed == []
    assert victim is not None
    assert set(report.deleted) >= set(ids) - {victim}
    assert set(report.deleted) <= set(ids)
    assert count(client, Song) == 0


def test_storage_removed_by_a_concurrent_sweep_counts_as_deleted(client, store, clock):
    ctx = client.app.state.ctx
    song_id = upload(client, b"gone", "g.wav").json()["id"]
    clock.advance(hours=25)

    class VanishingStorage:
        def __init__(self, inner) -> None:
            self.inner = inner

        def delete_song(self, sid: str) -> None:
            remove_everywhere(ctx, self.inner, sid)  # the other sweep wins the race...
            raise FileNotFoundError(sid)  # ...and our own removal finds nothing

        def __getattr__(self, name):
            return getattr(self.inner, name)

    ctx.storage = VanishingStorage(store)
    report = sweep_expired(ctx)

    assert report.deleted == [song_id]
    assert report.failed == []


def test_a_genuine_failure_with_data_still_present_stays_failed(client, store, clock):
    ctx = client.app.state.ctx
    song_id = upload(client, b"keep", "k.wav").json()["id"]
    clock.advance(hours=25)
    ctx.storage = FlakyStorage(store, {song_id})

    assert sweep_expired(ctx).failed == [song_id]
