import sqlite3

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from conftest import SECRET, alembic_config
from sqlalchemy import create_engine

from api.config import ConfigError, Settings, normalize_database_url
from api.models import Base


def test_signing_secret_is_required():
    with pytest.raises(ConfigError, match="SIGNING_SECRET"):
        Settings.from_env({})
    with pytest.raises(ConfigError):
        Settings.from_env({"SIGNING_SECRET": ""})


def test_settings_from_env():
    settings = Settings.from_env(
        {
            "SIGNING_SECRET": SECRET,
            "DATABASE_URL": "postgresql://u:p@db/x",
            "REDIS_URL": "redis://r:6379/1",
            "STORAGE_ROOT": "/data",
            "MAX_UPLOAD_MB": "5",
            "ALLOWED_EXTENSIONS": "wav, .MP3",
            "CORS_ORIGINS": "http://a.test, http://b.test",
            "DOWNLOAD_TOKEN_TTL_SECONDS": "999999",
        }
    )
    assert settings.database_url == "postgresql+psycopg://u:p@db/x"
    assert settings.max_upload_bytes == 5 * 1024 * 1024
    assert settings.allowed_extensions == {".wav", ".mp3"}
    assert settings.cors_origins == ("http://a.test", "http://b.test")
    assert settings.token_ttl_seconds == 24 * 3600


def test_settings_defaults():
    settings = Settings.from_env({"SIGNING_SECRET": SECRET})
    assert settings.max_upload_mb == 100
    assert ".wav" in settings.allowed_extensions
    assert settings.cors_origins == ()


def test_invalid_numbers_are_rejected():
    with pytest.raises(ConfigError):
        Settings.from_env({"SIGNING_SECRET": SECRET, "MAX_UPLOAD_MB": "abc"})
    with pytest.raises(ConfigError):
        Settings.from_env({"SIGNING_SECRET": SECRET, "MAX_UPLOAD_MB": "0"})


def test_normalize_database_url():
    assert normalize_database_url("sqlite:///x.db") == "sqlite:///x.db"
    assert normalize_database_url("postgres://h/d") == "postgresql+psycopg://h/d"


def test_alembic_upgrade_and_downgrade_on_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.sqlite'}"
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")

    tables = {
        row[0]
        for row in sqlite3.connect(tmp_path / "m.sqlite").execute(
            "select name from sqlite_master where type='table'"
        )
    }
    assert {"songs", "jobs", "packs", "sections_state", "alembic_version"} <= tables

    command.downgrade(cfg, "base")
    remaining = {
        row[0]
        for row in sqlite3.connect(tmp_path / "m.sqlite").execute(
            "select name from sqlite_master where type='table'"
        )
    }
    assert remaining == {"alembic_version"}


def test_migration_matches_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'd.sqlite'}"
    command.upgrade(alembic_config(url), "head")
    engine = create_engine(url)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_openapi_exposes_the_documented_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths) == {
        "/songs",
        "/songs/{song_id}",
        "/songs/{song_id}/analyze",
        "/songs/{song_id}/separate",
        "/songs/{song_id}/stagepack",
        "/songs/{song_id}/analysis",
        "/songs/{song_id}/sections",
        "/jobs/{job_id}",
        "/files/{token}",
    }
