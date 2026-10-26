"""Environment configuration.

``SIGNING_SECRET`` has no default on purpose: a missing secret must stop the service at startup.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/multitrack"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_STORAGE_ROOT = "./storage"
DEFAULT_EXTENSIONS = ".wav,.mp3,.flac,.m4a,.aac,.ogg,.aif,.aiff"
MAX_TOKEN_TTL_SECONDS = 24 * 3600
SONG_TTL_HOURS = 24
DEFAULT_LOST_JOB_GRACE_SECONDS = 300


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def normalize_database_url(url: str) -> str:
    """Route bare ``postgresql://`` URLs to the psycopg 3 driver this project installs."""
    for bare in ("postgresql://", "postgres://"):
        if url.startswith(bare):
            return "postgresql+psycopg://" + url[len(bare) :]
    return url


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def cors_origins_from_env(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    return _csv((env if env is not None else os.environ).get("CORS_ORIGINS", ""))


@dataclass(frozen=True)
class Settings:
    signing_secret: str
    database_url: str = DEFAULT_DATABASE_URL
    redis_url: str = DEFAULT_REDIS_URL
    storage_root: Path = Path(DEFAULT_STORAGE_ROOT)
    max_upload_mb: int = 100
    allowed_extensions: frozenset[str] = frozenset(_csv(DEFAULT_EXTENSIONS))
    cors_origins: tuple[str, ...] = ()
    # Lifetime of a download token; always capped by 24 h and by the song expiry.
    token_ttl_seconds: int = 3600
    song_ttl_hours: int = SONG_TTL_HOURS
    # A non-terminal job the queue no longer knows is marked failed after this many seconds.
    lost_job_grace_seconds: int = DEFAULT_LOST_JOB_GRACE_SECONDS

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = env if env is not None else os.environ
        secret = env.get("SIGNING_SECRET", "")
        if not secret:
            raise ConfigError("SIGNING_SECRET is required")
        try:
            max_mb = int(env.get("MAX_UPLOAD_MB", "100"))
            ttl = int(env.get("DOWNLOAD_TOKEN_TTL_SECONDS", "3600"))
            grace = int(env.get("LOST_JOB_GRACE_SECONDS", str(DEFAULT_LOST_JOB_GRACE_SECONDS)))
        except ValueError as exc:
            raise ConfigError(f"invalid numeric setting: {exc}") from exc
        if max_mb <= 0 or ttl <= 0:
            raise ConfigError("MAX_UPLOAD_MB and DOWNLOAD_TOKEN_TTL_SECONDS must be positive")
        if grace < 0:
            raise ConfigError("LOST_JOB_GRACE_SECONDS must be >= 0")
        extensions = frozenset(
            e.lower() if e.startswith(".") else f".{e.lower()}"
            for e in _csv(env.get("ALLOWED_EXTENSIONS", DEFAULT_EXTENSIONS))
        )
        return cls(
            signing_secret=secret,
            database_url=normalize_database_url(env.get("DATABASE_URL", DEFAULT_DATABASE_URL)),
            redis_url=env.get("REDIS_URL", DEFAULT_REDIS_URL),
            storage_root=Path(env.get("STORAGE_ROOT", DEFAULT_STORAGE_ROOT)),
            max_upload_mb=max_mb,
            allowed_extensions=extensions,
            cors_origins=cors_origins_from_env(env),
            token_ttl_seconds=min(ttl, MAX_TOKEN_TTL_SECONDS),
            lost_job_grace_seconds=grace,
        )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024
