from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app
from api.queueing import RemoteJob

API_ROOT = Path(__file__).resolve().parents[1]
SECRET = "test-signing-secret-0123456789"


def alembic_config(database_url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


class Clock:
    def __init__(self) -> None:
        self.current = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


@dataclass
class FakeQueue:
    """In-memory JobQueue double: captures enqueues and serves scripted RQ job state."""

    enqueued: list[dict] = field(default_factory=list)
    remote: dict[str, RemoteJob] = field(default_factory=dict)
    fail_enqueue: Exception | None = None

    def enqueue(self, func, args, kwargs, *, job_id, timeout):
        if self.fail_enqueue is not None:
            raise self.fail_enqueue
        self.enqueued.append(
            {"func": func, "args": args, "kwargs": kwargs, "job_id": job_id, "timeout": timeout}
        )

    def fetch(self, job_id):
        return self.remote.get(job_id)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def queue() -> FakeQueue:
    return FakeQueue()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        signing_secret=SECRET,
        database_url=f"sqlite:///{tmp_path / 'api.sqlite'}",
        storage_root=tmp_path / "storage",
        max_upload_mb=1,
        cors_origins=("http://localhost:3000",),
    )


@pytest.fixture
def client(settings: Settings, queue: FakeQueue, clock: Clock):
    command.upgrade(alembic_config(settings.database_url), "head")
    with TestClient(create_app(settings, queue=queue, clock=clock)) as test_client:
        yield test_client


@pytest.fixture
def store(client: TestClient):
    return client.app.state.ctx.storage


def upload(client: TestClient, content: bytes = b"RIFFdata-one", name: str = "Song One.wav"):
    return client.post("/songs", files={"file": (name, content, "audio/wav")})


@pytest.fixture
def song(client: TestClient) -> dict:
    response = upload(client)
    assert response.status_code == 201
    return response.json()
