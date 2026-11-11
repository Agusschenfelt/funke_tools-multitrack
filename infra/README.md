# Local stack

Services: `redis` (password protected), `postgres`, `api` (FastAPI) and `worker-cpu` (RQ worker on
queue `cpu`). Only the API port (8000) is published; Redis and Postgres are reachable inside the
compose network only. Song expiry is owned by the API (see "Cleanup" below).

## Run

```sh
cp infra/.env.example infra/.env     # then replace every placeholder:
                                     # POSTGRES_PASSWORD, SIGNING_SECRET (openssl rand -hex 32)
                                     # and REDIS_PASSWORD (openssl rand -hex 24, URL-safe hex only)
docker compose -f infra/docker-compose.yml up --build
```

The API listens on <http://localhost:8000> (OpenAPI at `/docs`). On start it runs
`alembic upgrade head`, then uvicorn. Compose waits for healthy postgres and redis first.

Validate the file without a daemon:

```sh
docker compose -f infra/docker-compose.yml --env-file infra/.env.example config
```

## Environment

Compose reads `infra/.env` (the project directory is `infra/`). Variables: `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_DB`, `SIGNING_SECRET` (required; the API refuses to start unless
it is at least 32 characters and not a placeholder; `ALLOW_INSECURE_SIGNING_SECRET=1` bypasses the
check for local development only), `REDIS_PASSWORD` (required; use URL-safe characters such as
`openssl rand -hex 24`, because it is embedded in `REDIS_URL`), `CORS_ORIGINS`,
`CLEANUP_INTERVAL_SECONDS`, `LOST_JOB_GRACE_SECONDS`, and the abuse limits `UPLOAD_RATE_LIMIT_PER_HOUR`,
`JOB_RATE_LIMIT_PER_HOUR` (per client IP, fixed one-hour window kept in Redis; 429 with
`Retry-After`; 0 disables; the limiter allows requests if Redis is down), `MAX_QUEUE_DEPTH` (new jobs
get 503 while more than this many wait; 0 disables) and `TRUST_PROXY_HEADERS` (1 reads the client
IP from the right-most `X-Forwarded-For` entry; set it only behind a proxy you control). The dev
compose disables the rate limits; the prod compose defaults to 10 uploads and 30 jobs per hour.
`DATABASE_URL`, `REDIS_URL` and `STORAGE_ROOT` are derived inside the compose file so hostnames
always match the services. `CUES_DIR` is optional and left unset: the worker image ships
`assets/cues` and audio-core finds it relative to its source tree (`CUES_DIR` points at a single
language directory, so it cannot serve both `en` and `es`).

## Queue security

The worker executes the jobs it finds in Redis, so Redis is treated as a trust boundary:

- Redis is not published on the host and requires `REDIS_PASSWORD` (`requirepass`).
- Job records are JSON (never pickle) on both the API and the worker.
- The worker only runs `worker_cpu.jobs.analyze_job`, `separate_job` and `stagepack_job`; any other
  function name in a job record fails the job before anything is imported.

To debug from the host, opt in to loopback-only ports for Redis and Postgres:

```sh
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file infra/.env up -d
```

## Cleanup

The API sweep (every `CLEANUP_INTERVAL_SECONDS`) deletes expired songs with their rows and files,
and holds back a song with a queued or running job for up to one hour past expiry. There is no
separate cleanup service: a second deleter that ignores in-flight jobs would defeat that margin.
`python -m worker_cpu.cleanup` remains as a manual orphan sweep (storage only): it removes song
directories older than the song TTL + 6 h whose rows the API no longer tracks, and skips songs
with a live job lock (`jobs/<job_id>.lock`):

```sh
docker compose -f infra/docker-compose.yml run --rm worker-cpu python -m worker_cpu.cleanup
```

Jobs also write `jobs/<job_id>.json` on success; the API reads only that marker to recover the
outcome of a job RQ has forgotten.

## Volumes

- `storage` mounted at `/data` in `api` and `worker-cpu` (`STORAGE_ROOT`).
- `model_cache` mounted at `/cache` in `worker-cpu` (`TORCH_HOME=/cache/torch`).
- `postgres_data` for the database.

`docker compose ... down -v` deletes all three.

## First run: model downloads

Model weights (Demucs, beat_this) are not baked into the image. The first analysis or
separation job downloads them into `model_cache`, so it is slow and needs internet access from
the worker container. Later jobs and restarts reuse the cache.

## Images

- API: python 3.11-slim, no torch, no ffmpeg (the API never decodes audio).
- Worker: python 3.11-slim + ffmpeg, libsndfile, libgomp; runs as a non-root user; limited to
  2 CPUs (`cpus: 2`) and 2 BLAS/OMP threads.
- Both build with the repository root as context
  (`docker build -f apps/api/Dockerfile .`) and install with `uv sync --frozen --no-dev`.
  A single root `.dockerignore` applies to both.

### Image sizes (built on the Intel Mac)

API 694 MB (no torch); worker-cpu 2.9 GB.

### CPU-only torch

On Linux, `torch` and `torchaudio` resolve from the PyTorch CPU index
(`https://download.pytorch.org/whl/cpu`) through `[[tool.uv.index]]` (`explicit = true`) and
`[tool.uv.sources]` with a `sys_platform == 'linux'` marker, in both `packages/audio-core` and
`workers/cpu` (uv only honors the sources of the project being locked). The lock has no `nvidia-*`
or `triton` packages; this took the worker image from 10.5 GB to 2.9 GB. The torch version
(2.14.1+cpu) still satisfies the `>=2.6` CVE-2025-32434 floor. Intel macOS still resolves PyPI
torch 2.2.2.

## Status and follow-ups

- Images are built and the end-to-end smoke test passes against the running stack
  (`scripts/e2e_smoke.py`: upload, analyze with sections, edit sections, separate with
  `htdemucs_6s`, stage pack ZIP checks, negative checks). With Docker limited to 2 CPUs the
  separation of a 32 s song takes about 200 s (roughly 6 s per audio second); production needs a GPU.
- Follow-up: pin the `ghcr.io/astral-sh/uv` image by digest.
- Follow-up: bake the model weights into the image (or a pre-download step) so the first job does
  not spend minutes downloading them.
