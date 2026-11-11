"""Per-client-IP fixed-window rate limits backed by Redis.

Fails open: if Redis cannot be reached the request is allowed and the outage is logged, since the
limiter protects capacity and must not take uploads down with it.
"""

import ipaddress
import logging
from typing import Protocol

from fastapi import Depends, HTTPException, Request

from api.config import RATE_LIMIT_WINDOW_SECONDS, Settings
from api.deps import Ctx

log = logging.getLogger(__name__)


class RateLimiter(Protocol):
    def hit(self, key: str, limit: int, window_seconds: int) -> int:
        """Count one request; 0 when allowed, else the seconds until the window resets."""
        ...


class RedisRateLimiter:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._connection = None

    def _conn(self):
        from redis import Redis

        if self._connection is None:
            self._connection = Redis.from_url(
                self.redis_url, socket_connect_timeout=1, socket_timeout=1
            )
        return self._connection

    def hit(self, key: str, limit: int, window_seconds: int) -> int:
        from redis.exceptions import RedisError

        try:
            conn = self._conn()
            count = conn.incr(key)
            ttl = conn.ttl(key)
            if count == 1 or ttl < 0:  # first hit, or a key left without expiry
                conn.expire(key, window_seconds)
                ttl = window_seconds
        except RedisError:
            log.warning("rate limiter unavailable (Redis); allowing request", exc_info=True)
            return 0
        return 0 if count <= limit else max(ttl, 1)


def _normalize(value: str) -> str | None:
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if address.version == 6:  # a /64 is one subscriber; do not let them rotate through it
        return str(ipaddress.ip_network(f"{address}/64", strict=False).network_address)
    return str(address)


def client_ip(request: Request, settings: Settings) -> str:
    """The TCP peer, or with ``trust_proxy_headers`` the right-most X-Forwarded-For entry.

    The proxy appends the address it saw as the last entry; anything to its left is client-supplied
    and spoofable, so only the last one is read. An unparsable value falls back to the peer.
    """
    peer = request.client.host if request.client else "unknown"
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        parsed = _normalize(forwarded.rsplit(",", 1)[-1]) if forwarded else None
        if parsed:
            return parsed
    return _normalize(peer) or peer


def _limit(scope: str, attribute: str):
    def dependency(request: Request, ctx: Ctx) -> None:
        limit = getattr(ctx.settings, attribute)
        if limit <= 0:
            return
        key = f"ratelimit:{scope}:{client_ip(request, ctx.settings)}"
        retry_after = ctx.limiter.hit(key, limit, RATE_LIMIT_WINDOW_SECONDS)
        if retry_after:
            raise HTTPException(
                429, "too many requests; try again later", headers={"Retry-After": str(retry_after)}
            )

    return Depends(dependency)


UploadLimit = _limit("upload", "upload_rate_limit")
JobLimit = _limit("job", "job_rate_limit")
