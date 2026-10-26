# Local stack

Services: `redis`, `postgres`, `api` (FastAPI), `worker-cpu` (RQ worker on queue `cpu`) and `cleanup`
(a sidecar that runs `python -m worker_cpu.cleanup` every `CLEANUP_INTERVAL_SECONDS`).

## Run

```sh
cp infra/.env.example infra/.env     # then set POSTGRES_PASSWORD and SIGNING_SECRET
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
`POSTGRES_PASSWORD`, `POSTGRES_DB`, `SIGNING_SECRET` (required, the API refuses to start
without it), `CORS_ORIGINS`, `CLEANUP_INTERVAL_SECONDS`, `LOST_JOB_GRACE_SECONDS`.
`DATABASE_URL`, `REDIS_URL` and `STORAGE_ROOT` are derived inside the compose file so hostnames
always match the services. `CUES_DIR` is optional and left unset: the worker image ships
`assets/cues` and audio-core finds it relative to its source tree (`CUES_DIR` points at a single
language directory, so it cannot serve both `en` and `es`).

## Volumes

- `storage` mounted at `/data` in `api`, `worker-cpu` and `cleanup` (`STORAGE_ROOT`).
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

### Image size caveat

`workers/cpu/uv.lock` resolves Linux torch (2.14.x) and torchaudio from PyPI. Those Linux
wheels pull the CUDA runtime packages (`nvidia-*`, `triton`), which adds several GB to the
worker image even though it only runs on CPU. The torch version still satisfies the `>=2.6`
CVE-2025-32434 floor.

## Status and follow-ups

- Images have not been built yet (no Docker daemon was available when this was written);
  `docker compose config` is the only check done. Build and smoke run are pending.
- Follow-up: CPU-only wheels. Add a `pytorch-cpu` index
  (`https://download.pytorch.org/whl/cpu`, `explicit = true`) to the worker project and pin
  `torch`/`torchaudio` to it with `tool.uv.sources` for Linux (marker
  `sys_platform == 'linux'`), then re-lock. This needs a pyproject/lock change, so it was not
  done here. The Intel macOS pin is unaffected.
- Follow-up: pin the `ghcr.io/astral-sh/uv` image by digest.
