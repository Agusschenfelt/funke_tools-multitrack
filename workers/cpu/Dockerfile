# syntax=docker/dockerfile:1
# Build from the repository root:
#   docker build -f workers/cpu/Dockerfile -t multitrack-worker-cpu .
FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

# ffmpeg decodes uploads; libsndfile1 backs soundfile; libgomp1 is needed by torch and numba.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app
# audio-core resolves assets/cues relative to its source tree (parents[3]), so keep the repo layout.
COPY packages/audio-core packages/audio-core
COPY assets/cues assets/cues
COPY workers/cpu workers/cpu

WORKDIR /app/workers/cpu
# Linux resolves torch>=2.6 +cpu wheels from the PyTorch CPU index (see [tool.uv.sources] in workers/cpu/pyproject.toml).
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# /cache holds model weights (torch hub, demucs, beat_this); mount a volume there.
RUN useradd --system --uid 10001 --create-home app \
    && mkdir -p /data /cache && chown app:app /data /cache
USER app

ENV STORAGE_ROOT=/data \
    TORCH_HOME=/cache/torch \
    XDG_CACHE_HOME=/cache \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2

CMD ["python", "-m", "worker_cpu"]
