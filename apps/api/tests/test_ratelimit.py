import logging
from dataclasses import dataclass, field, replace

import pytest
from alembic import command
from conftest import alembic_config, upload
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.requests import Request

from api.config import ConfigError, Settings
from api.main import create_app
from api.ratelimit import RedisRateLimiter, client_ip


@dataclass
class MemoryLimiter:
    counts: dict[str, int] = field(default_factory=dict)
    keys: list[str] = field(default_factory=list)

    def hit(self, key, limit, window_seconds):
        self.keys.append(key)
        self.counts[key] = self.counts.get(key, 0) + 1
        return 0 if self.counts[key] <= limit else window_seconds


def make_client(settings, queue, clock, limiter, **overrides):
    configured = replace(settings, **overrides)
    command.upgrade(alembic_config(configured.database_url), "head")
    return TestClient(create_app(configured, queue=queue, clock=clock, limiter=limiter))


def test_uploads_over_the_limit_get_429_with_retry_after(settings, queue, clock):
    with make_client(settings, queue, clock, MemoryLimiter(), upload_rate_limit=2) as client:
        assert upload(client, b"RIFF-a").status_code == 201
        assert upload(client, b"RIFF-b").status_code == 201
        blocked = upload(client, b"RIFF-c")
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "3600"


def test_job_creation_over_the_limit_gets_429_but_uploads_are_separate(settings, queue, clock):
    limiter = MemoryLimiter()
    with make_client(settings, queue, clock, limiter, job_rate_limit=1) as client:
        song = upload(client).json()
        store = client.app.state.ctx.storage
        store.put_bytes(song["id"], "source.wav", b"x")
        first = client.post(f"/songs/{song['id']}/separate", json={})
        second = client.post(f"/songs/{song['id']}/separate", json={})
    assert first.status_code == 202
    assert second.status_code == 429
    assert "Retry-After" in second.headers


def test_limits_are_per_client_ip(settings, queue, clock):
    limiter = MemoryLimiter()
    with make_client(
        settings, queue, clock, limiter, upload_rate_limit=1, trust_proxy_headers=True
    ) as client:
        a = upload(client, b"RIFF-a")
        again = client.post(
            "/songs", files={"file": ("x.wav", b"RIFF-b")}, headers={"x-forwarded-for": "9.9.9.9"}
        )
        blocked = upload(client, b"RIFF-c")
    assert (a.status_code, again.status_code, blocked.status_code) == (201, 201, 429)


def test_zero_disables_the_limit(settings, queue, clock):
    with make_client(settings, queue, clock, MemoryLimiter(), upload_rate_limit=0) as client:
        assert all(upload(client, b"RIFF-%d" % i).status_code == 201 for i in range(5))


def test_queue_over_the_cap_refuses_new_jobs_with_503(settings, queue, clock):
    with make_client(settings, queue, clock, MemoryLimiter(), max_queue_depth=2) as client:
        song = upload(client).json()
        client.app.state.ctx.storage.put_bytes(song["id"], "source.wav", b"x")
        queue.queued = 2
        at_cap = client.post(f"/songs/{song['id']}/separate", json={})
        queue.queued = 3
        over = client.post(f"/songs/{song['id']}/separate", json={})
    assert at_cap.status_code == 202
    assert over.status_code == 503
    assert over.headers["retry-after"] == "60"
    assert len(queue.enqueued) == 1


def _request(peer: str, forwarded: str | None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


def test_client_ip_uses_the_peer_by_default():
    settings = Settings(signing_secret="s")
    assert client_ip(_request("10.0.0.5", "1.2.3.4"), settings) == "10.0.0.5"


def test_client_ip_trusts_only_the_rightmost_forwarded_entry():
    settings = Settings(signing_secret="s", trust_proxy_headers=True)
    request = _request("172.18.0.2", "6.6.6.6, 203.0.113.7")
    assert client_ip(request, settings) == "203.0.113.7"


@pytest.mark.parametrize("forwarded", [None, "", "not-an-ip"])
def test_client_ip_falls_back_to_the_peer_without_a_usable_header(forwarded):
    settings = Settings(signing_secret="s", trust_proxy_headers=True)
    assert client_ip(_request("172.18.0.2", forwarded), settings) == "172.18.0.2"


def test_ipv6_clients_share_a_limit_per_64_prefix():
    settings = Settings(signing_secret="s")
    a = client_ip(_request("2001:db8:1:2::1", None), settings)
    b = client_ip(_request("2001:db8:1:2:ffff::9", None), settings)
    assert a == b


class FakeRedis:
    def __init__(self):
        self.values: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def incr(self, key):
        self.values[key] = self.values.get(key, 0) + 1
        self.ttls.setdefault(key, -1)
        return self.values[key]

    def ttl(self, key):
        return self.ttls[key]

    def expire(self, key, seconds):
        self.ttls[key] = seconds


def test_redis_limiter_counts_in_a_fixed_window():
    limiter = RedisRateLimiter("redis://unused")
    limiter._connection = FakeRedis()
    assert [limiter.hit("k", 2, 3600) for _ in range(3)] == [0, 0, 3600]


def test_redis_limiter_fails_open_and_logs(caplog):
    class Down:
        def incr(self, key):
            raise RedisConnectionError("down")

    limiter = RedisRateLimiter("redis://unused")
    limiter._connection = Down()
    with caplog.at_level(logging.WARNING, logger="api.ratelimit"):
        assert limiter.hit("k", 1, 3600) == 0
    assert "rate limiter unavailable" in caplog.text


def test_env_defaults_and_overrides():
    base = {"SIGNING_SECRET": "x" * 40}
    defaults = Settings.from_env(base)
    assert (defaults.upload_rate_limit, defaults.job_rate_limit) == (10, 30)
    assert (defaults.max_queue_depth, defaults.trust_proxy_headers) == (20, False)
    custom = Settings.from_env(
        {
            **base,
            "UPLOAD_RATE_LIMIT_PER_HOUR": "3",
            "JOB_RATE_LIMIT_PER_HOUR": "4",
            "MAX_QUEUE_DEPTH": "0",
            "TRUST_PROXY_HEADERS": "1",
        }
    )
    assert (custom.upload_rate_limit, custom.job_rate_limit, custom.max_queue_depth) == (3, 4, 0)
    assert custom.trust_proxy_headers is True
    with pytest.raises(ConfigError):
        Settings.from_env({**base, "MAX_QUEUE_DEPTH": "-1"})
