"""What this worker is willing to execute, and how jobs are serialized.

RQ runs whatever dotted path a job record names, so anyone who can write to Redis could otherwise
make the worker import and call any function in its environment. Two defenses, both applied by the
entry point (``__main__``) and by the API's queue:

* ``JSON_SERIALIZER``: job records are JSON, never pickle, so a forged record cannot smuggle in
  code through deserialization. The API's queue (``api.queueing``) must use the same serializer,
  or the worker could not read its jobs; that is the API's only part in this.
* ``AllowlistJob``: the worker resolves a job's function only if it is one of ``ALLOWED_JOBS``,
  and never resolves a callback. Anything else fails the job before any import happens. This
  runs in the worker alone: the API cannot enforce it against someone who writes to Redis.

Redis itself also requires a password (see ``infra/``); these two checks are defense in depth.

Every place RQ 2.12 imports a callable named by a job record, and what is done about it:

* ``Job.func`` (``func_name``, or ``getattr(instance, func_name)``): checked against the allowlist.
* ``Job.success_callback`` / ``failure_callback`` / ``stopped_callback``: each does
  ``import_attribute(<x>_callback_name)`` lazily; the worker reads them after a job succeeds,
  fails or is stopped. Blocked below: ``func`` refuses a record that sets any of them, and the
  three properties never import (they return ``None``).

Not record-controlled: dependencies (``dependency_ids`` are job ids, not dotted paths), the job
and queue classes and the serializer (chosen by the worker's own configuration).
"""

from rq.job import Job
from rq.serializers import JSONSerializer

JSON_SERIALIZER = JSONSerializer

ALLOWED_JOBS = frozenset(
    {
        "worker_cpu.jobs.analyze_job",
        "worker_cpu.jobs.separate_job",
        "worker_cpu.jobs.stagepack_job",
    }
)


class DisallowedJobError(RuntimeError):
    """A job record names a function this worker does not run."""


class AllowlistJob(Job):
    """An RQ job that only resolves functions in ``ALLOWED_JOBS`` and never resolves callbacks."""

    @property
    def func(self):
        name = self.func_name
        # A missing name is rejected too: the base class would return None and skip resolution.
        if name is None or name not in ALLOWED_JOBS:
            raise DisallowedJobError(f"function not allowed on this worker: {name!r}")
        # ``instance`` makes RQ call ``getattr(instance, name)`` instead of importing ``name``, so
        # an allowlisted name could be redirected to an arbitrary bound method. Our own jobs are
        # plain module functions and never carry an instance.
        if self.instance is not None:
            raise DisallowedJobError(f"job carries an instance, not allowed: {name!r}")
        for field in ("success", "failure", "stopped"):
            if getattr(self, f"_{field}_callback_name"):
                raise DisallowedJobError(f"{field} callbacks are not allowed on this worker")
        return super().func

    # Backstop for code paths that read a callback without going through ``func`` (for example
    # failure handling): never import a name taken from a job record.
    @property
    def success_callback(self):
        return None

    @property
    def failure_callback(self):
        return None

    @property
    def stopped_callback(self):
        return None
