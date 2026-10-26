import json
import zlib

import fakeredis
import pytest
from rq import Queue, SimpleWorker
from rq.job import JobStatus

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
