import json
import sys
import zlib

import fakeredis
import pytest
from rq import Queue, SimpleWorker
from rq.job import Job, JobStatus

from worker_cpu import jobs
from worker_cpu.__main__ import build_worker
from worker_cpu.security import ALLOWED_JOBS, JSON_SERIALIZER, AllowlistJob


@pytest.fixture
def connection() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()


def queue_of(connection) -> Queue:
    return Queue("cpu", connection=connection, job_class=AllowlistJob, serializer=JSON_SERIALIZER)


def run_burst(connection) -> None:
    worker = build_worker(connection, SimpleWorker)
    worker.work(burst=True)


@pytest.mark.parametrize("func", ["os.system", "builtins.eval", "nonexistent_pkg.attack"])
def test_functions_outside_the_allowlist_fail_before_any_import(connection, func) -> None:
    job = queue_of(connection).enqueue(func, "echo pwned")
    run_burst(connection)

    job.refresh()
    assert job.get_status() == JobStatus.FAILED
    # DisallowedJobError (not ModuleNotFoundError) proves the check ran before importing anything.
    assert "DisallowedJobError" in job.latest_result().exc_string


def test_helpers_inside_the_jobs_module_are_not_runnable(connection) -> None:
    job = queue_of(connection).enqueue("worker_cpu.jobs.get_storage")
    run_burst(connection)

    job.refresh()
    assert job.get_status() == JobStatus.FAILED
    assert "DisallowedJobError" in job.latest_result().exc_string


def test_allowlisted_jobs_still_run(connection, storage_root, fake_models, song) -> None:
    job = queue_of(connection).enqueue("worker_cpu.jobs.separate_job", song)
    run_burst(connection)

    job.refresh()
    assert job.get_status() == JobStatus.FINISHED
    assert job.return_value()["song_id"] == song


def test_allowlist_names_exist_in_the_jobs_module() -> None:
    for name in ALLOWED_JOBS:
        assert callable(getattr(jobs, name.rsplit(".", 1)[1]))


def test_job_records_are_json_so_pickle_payloads_are_never_loaded(connection) -> None:
    job = queue_of(connection).enqueue("worker_cpu.jobs.analyze_job", "s1")
    raw = connection.hget(f"rq:job:{job.id}", "data")
    assert json.loads(zlib.decompress(raw))  # pickle bytes would not parse as JSON


# --- forged records: no field of a job record may make the worker import an arbitrary name -----

SENTINEL = "sentinel_import_probe"


@pytest.fixture
def import_probe(tmp_path, monkeypatch):
    """A module that records an import in a file; any import of it is a security failure."""
    marker = tmp_path / "imported"
    (tmp_path / f"{SENTINEL}.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('x')\n"
        "def attack(*a, **k):\n    return 'pwned'\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, SENTINEL, raising=False)
    yield marker
    sys.modules.pop(SENTINEL, None)


def forge(connection, **fields) -> Job:
    """Enqueue a legitimate job, then overwrite fields of its stored record."""
    job = queue_of(connection).enqueue("worker_cpu.jobs.analyze_job", "s1")
    for key, value in fields.items():
        if value is None:
            connection.hdel(job.key, key)
        else:
            connection.hset(job.key, key, value)
    return job


def forge_func_name(connection, func_name) -> Job:
    """Replace the function name inside the stored ``[func_name, instance, args, kwargs]``."""
    job = queue_of(connection).enqueue("worker_cpu.jobs.analyze_job", "s1")
    data = json.loads(zlib.decompress(connection.hget(job.key, "data")))
    data[0] = func_name
    connection.hset(job.key, "data", zlib.compress(json.dumps(data).encode()))
    return job


def assert_rejected_without_import(connection, job, marker) -> None:
    run_burst(connection)
    job.refresh()
    assert job.get_status() == JobStatus.FAILED
    assert "DisallowedJobError" in job.latest_result().exc_string
    assert not marker.exists()
    assert SENTINEL not in sys.modules


def test_record_without_a_function_name_is_rejected(connection, import_probe) -> None:
    job = forge_func_name(connection, None)
    assert_rejected_without_import(connection, job, import_probe)


def test_record_with_a_disallowed_function_is_rejected_without_import(
    connection, import_probe
) -> None:
    job = forge_func_name(connection, f"{SENTINEL}.attack")
    assert_rejected_without_import(connection, job, import_probe)


@pytest.mark.parametrize("field", ["success", "failure", "stopped"])
def test_callbacks_in_a_record_are_never_imported(connection, import_probe, field) -> None:
    job = forge(connection, **{f"{field}_callback_name": f"{SENTINEL}.attack"})
    assert_rejected_without_import(connection, job, import_probe)


@pytest.mark.parametrize("field", ["success", "failure", "stopped"])
def test_callback_properties_never_import(connection, import_probe, field) -> None:
    job = forge(connection, **{f"{field}_callback_name": f"{SENTINEL}.attack"})
    fetched = AllowlistJob.fetch(job.id, connection=connection, serializer=JSON_SERIALIZER)
    assert getattr(fetched, f"{field}_callback") is None
    assert not import_probe.exists()
