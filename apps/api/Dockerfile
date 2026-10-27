# syntax=docker/dockerfile:1
# Build from the repository root:
#   docker build -f apps/api/Dockerfile -t multitrack-api .
# Light image: no torch, demucs or ffmpeg (the API never decodes audio).
FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app
# audio-core is an editable path dependency (../../packages/audio-core), so keep the repo layout.
COPY packages/audio-core packages/audio-core
COPY apps/api apps/api

WORKDIR /app/apps/api
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

RUN useradd --system --uid 10001 --create-home app \
    && mkdir -p /data && chown app:app /data
USER app

ENV STORAGE_ROOT=/data
EXPOSE 8000

# Migrate, then serve. exec keeps uvicorn as PID 1 so it receives SIGTERM.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn api.main:app --host 0.0.0.0 --port 8000"]
