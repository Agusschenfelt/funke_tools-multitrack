import sqlite3

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from conftest import SECRET, alembic_config
from sqlalchemy import create_engine

from api.config import ConfigError, Settings, check_signing_secret, normalize_database_url
from api.models import Base


def test_signing_secret_is_required():
    with pytest.raises(ConfigError, match="SIGNING_SECRET"):
        Settings.from_env({})
    with pytest.raises(ConfigError):
        Settings.from_env({"SIGNING_SECRET": ""})


@pytest.mark.parametrize(
    "secret",
    ["short", "x" * 31, "changeme" + "0" * 40, "Change-Me-" + "0" * 40, "replace-this-" + "0" * 30],
)
def test_weak_or_placeholder_signing_secret_is_refused_with_a_fix(secret):
    with pytest.raises(ConfigError, match=r"openssl rand -hex 32"):
        Settings.from_env({"SIGNING_SECRET": secret})


def test_a_random_secret_of_minimum_length_is_accepted():
    check_signing_secret("a" * 32, {})
    assert Settings.from_env({"SIGNING_SECRET": "a" * 32}).signing_secret == "a" * 32


@pytest.mark.parametrize("secret", ["short", "changeme"])
def test_insecure_secret_escape_hatch_allows_weak_values_only_when_set_to_1(secret):
    env = {"SIGNING_SECRET": secret, "ALLOW_INSECURE_SIGNING_SECRET": "1"}
    assert Settings.from_env(env).signing_secret == secret
    for off in ("0", "", "true"):
        with pytest.raises(ConfigError):
            Settings.from_env({**env, "ALLOW_INSECURE_SIGNING_SECRET": off})


def test_the_escape_hatch_does_not_allow_an_empty_secret():
    with pytest.raises(ConfigError, match="required"):
        Settings.from_env({"SIGNING_SECRET": "", "ALLOW_INSECURE_SIGNING_SECRET": "1"})


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
