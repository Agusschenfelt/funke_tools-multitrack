"""Signed, expiring download tokens (stdlib HMAC-SHA256).

Format: ``base64url(payload_json) "." base64url(hmac)`` where the payload is
``{"s": song_id, "n": artifact_name, "e": expiry_epoch_seconds}``. The MAC covers the encoded
payload and is domain-separated, so tokens cannot be forged without ``SIGNING_SECRET``.
"""

import base64
import binascii
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime

_DOMAIN = b"multitrack-download-v1:"


class TokenInvalid(ValueError):
    """Malformed, tampered or wrongly signed token."""


class TokenExpired(ValueError):
    """Correctly signed token past its expiry."""


@dataclass(frozen=True)
class Claims:
    song_id: str
    name: str
    expires_at: datetime


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(secret: str, encoded_payload: str) -> bytes:
    return hmac.new(
        secret.encode(), _DOMAIN + encoded_payload.encode("ascii"), hashlib.sha256
    ).digest()


def sign(secret: str, song_id: str, name: str, expires_at: datetime) -> str:
    payload = json.dumps(
        {"s": song_id, "n": name, "e": int(expires_at.timestamp())}, separators=(",", ":")
    )
    encoded = _b64(payload.encode())
    return f"{encoded}.{_b64(_mac(secret, encoded))}"


def verify(secret: str, token: str, now: datetime) -> Claims:
    # Tokens are pure ASCII; reject anything else before it reaches the ASCII-only MAC encoder.
    if not token.isascii():
        raise TokenInvalid("malformed token")
    try:
        encoded, signature = token.split(".")
        provided = _unb64(signature)
    except (ValueError, binascii.Error) as exc:
        raise TokenInvalid("malformed token") from exc
    if not hmac.compare_digest(provided, _mac(secret, encoded)):
        raise TokenInvalid("bad signature")
    try:
        data = json.loads(_unb64(encoded))
        claims = Claims(
            song_id=str(data["s"]),
            name=str(data["n"]),
            expires_at=datetime.fromtimestamp(int(data["e"]), UTC),
        )
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise TokenInvalid("malformed payload") from exc
    if now >= claims.expires_at:
        raise TokenExpired("token expired")
    return claims
