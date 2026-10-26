"""What this worker is willing to execute, and how jobs are serialized.

RQ runs whatever dotted path a job record names, so anyone who can write to Redis could otherwise
make the worker import and call any function in its environment. Two defenses, both applied by the
entry point (``__main__``) and by the API's queue:

* ``JSON_SERIALIZER``: job records are JSON, never pickle, so a forged record cannot smuggle in
  code through deserialization.
* ``AllowlistJob``: the worker resolves a job's function only if it is one of ``ALLOWED_JOBS``;
  anything else fails the job before any import happens.

Redis itself also requires a password (see ``infra/``); these two checks are defense in depth.
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
    """An RQ job that only resolves functions in ``ALLOWED_JOBS``."""

    @property
    def func(self):
        name = self.func_name
        if name is not None and (self.instance is not None or name not in ALLOWED_JOBS):
            raise DisallowedJobError(f"function not allowed on this worker: {name!r}")
        return super().func
