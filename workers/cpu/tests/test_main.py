import pytest

from worker_cpu import __main__ as entry
from worker_cpu import config
from worker_cpu.security import JSON_SERIALIZER, AllowlistJob


def test_redis_url_defaults_and_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert config.redis_url() == config.DEFAULT_REDIS_URL
    monkeypatch.setenv("REDIS_URL", "redis://cache:6380/2")
    assert config.redis_url() == "redis://cache:6380/2"


def test_main_runs_a_worker_on_the_cpu_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    import fakeredis

    seen: dict = {}

    class FakeWorker:
        def __init__(self, queues, connection, job_class, serializer) -> None:
            seen["queues"] = [q.name for q in queues]
            seen["job_class"] = job_class
            seen["serializer"] = serializer

        def work(self) -> None:
            seen["worked"] = True

    monkeypatch.setattr(entry.Redis, "from_url", lambda url: fakeredis.FakeRedis())
    monkeypatch.setattr(entry, "Worker", FakeWorker)
    entry.main()
    assert seen == {
        "queues": ["cpu"],
        "worked": True,
        "job_class": AllowlistJob,
        "serializer": JSON_SERIALIZER,
    }


def test_storage_root_selects_local_storage(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    storage = config.get_storage()
    storage.put_bytes("s1", "analysis.json", b"{}")
    assert (tmp_path / "s1" / "analysis.json").read_bytes() == b"{}"
