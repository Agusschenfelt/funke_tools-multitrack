from datetime import timedelta

import pytest
from conftest import SECRET

from api import tokens


@pytest.fixture
def pack(client, store, song):
    store.put_bytes(song["id"], "packs/Pack.zip", b"zip-content")
    store.put_bytes(song["id"], "stems/drums.wav", b"wav-content")
    artifacts = client.get(f"/songs/{song['id']}").json()["artifacts"]
    return {"pack": artifacts["packs"][0], "stem": artifacts["stems"][0], "song": song}


def test_signed_pack_download_streams_with_filename(client, pack):
    response = client.get(pack["pack"]["url"])

    assert response.status_code == 200
    assert response.content == b"zip-content"
    assert response.headers["content-type"] == "application/zip"
    assert 'filename="Pack.zip"' in response.headers["content-disposition"]


def test_signed_stem_download(client, pack):
    response = client.get(pack["stem"]["url"])
    assert response.status_code == 200
    assert response.content == b"wav-content"
    assert response.headers["content-type"] == "audio/wav"


def test_tampered_signature_is_403(client, pack):
    token = pack["pack"]["url"].removeprefix("/files/")
    payload, signature = token.split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
    assert client.get(f"/files/{payload}.{flipped}").status_code == 403


def test_tampered_payload_is_403(client, pack):
    token = pack["pack"]["url"].removeprefix("/files/")
    forged = tokens.sign(
        "another-secret", pack["song"]["id"], "packs/Pack.zip", client.app.state.ctx.now()
    )
    assert client.get(f"/files/{forged}").status_code == 403
    assert client.get(f"/files/{token[:-2]}").status_code == 403
    assert client.get("/files/garbage").status_code == 403
    assert client.get("/files/a.b").status_code == 403


def test_expired_token_is_410(client, clock, pack):
    clock.advance(seconds=client.app.state.ctx.settings.token_ttl_seconds + 1)
    assert client.get(pack["pack"]["url"]).status_code == 410


def test_token_expiry_is_ttl_capped_by_24_hours(client, pack):
    link = pack["pack"]
    ctx = client.app.state.ctx
    assert link["token_expires_at"] <= (ctx.now() + timedelta(hours=24)).isoformat().replace(
        "+00:00", "Z"
    )


def test_token_never_outlives_the_song(client, clock, settings, store, song):
    # Song expires in 10 minutes; token TTL would be an hour.
    clock.advance(hours=23, minutes=50)
    store.put_bytes(song["id"], "packs/Pack.zip", b"zip")
    link = client.get(f"/songs/{song['id']}").json()["artifacts"]["packs"][0]

    from datetime import datetime

    assert datetime.fromisoformat(link["token_expires_at"]) == datetime.fromisoformat(
        song["expires_at"]
    )
    clock.advance(minutes=11)
    assert client.get(link["url"]).status_code == 410


def test_token_cannot_reach_other_artifacts(client, store, song):
    store.put_bytes(song["id"], "source.wav", b"original")
    store.put_bytes(song["id"], "analysis.json", b"{}")
    ctx = client.app.state.ctx
    expiry = ctx.now() + timedelta(minutes=5)
    for name in ("source.wav", "analysis.json", "packs/../source.wav", "stems/../source.wav"):
        token = tokens.sign(SECRET, song["id"], name, expiry)
        assert client.get(f"/files/{token}").status_code == 403, name


def test_token_for_missing_file_is_404(client, song):
    expiry = client.app.state.ctx.now() + timedelta(minutes=5)
    token = tokens.sign(SECRET, song["id"], "packs/none.zip", expiry)
    assert client.get(f"/files/{token}").status_code == 404


def test_unknown_song_in_token_is_410(client):
    expiry = client.app.state.ctx.now() + timedelta(minutes=5)
    token = tokens.sign(SECRET, "3f2b8a7e-0000-4000-8000-000000000000", "packs/a.zip", expiry)
    assert client.get(f"/files/{token}").status_code == 410


def test_token_roundtrip_and_malformed_inputs():
    from datetime import UTC, datetime

    now = datetime(2026, 1, 1, tzinfo=UTC)
    token = tokens.sign("s", "song", "packs/a.zip", now + timedelta(seconds=10))
    claims = tokens.verify("s", token, now)
    assert (claims.song_id, claims.name) == ("song", "packs/a.zip")
    with pytest.raises(tokens.TokenExpired):
        tokens.verify("s", token, now + timedelta(seconds=10))
    with pytest.raises(tokens.TokenInvalid):
        tokens.verify("other", token, now)
    with pytest.raises(tokens.TokenInvalid):
        tokens.verify("s", "no-dot", now)
