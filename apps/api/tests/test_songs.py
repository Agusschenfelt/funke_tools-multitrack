import hashlib
from datetime import timedelta

from conftest import upload


def test_upload_creates_song_and_stores_source(client, store):
    content = b"RIFF" + b"x" * 5000
    response = upload(client, content, "My Song.WAV")

    assert response.status_code == 201
    body = response.json()
    assert body["reused"] is False
    assert body["filename"] == "My Song.WAV"
    assert body["sha256"] == hashlib.sha256(content).hexdigest()
    assert body["duration"] is None
    created, expires = body["created_at"], body["expires_at"]
    assert created < expires
    # Stored with the worker's layout: source.<ext> under the song id.
    assert store.get_bytes(body["id"], "source.wav") == content


def test_expires_exactly_24_hours_after_creation(client, clock, song):
    from datetime import datetime

    created = datetime.fromisoformat(song["created_at"])
    expires = datetime.fromisoformat(song["expires_at"])
    assert expires - created == timedelta(hours=24)


def test_same_hash_is_reused_within_24_hours(client, clock, store):
    first = upload(client, b"same-bytes", "a.wav").json()
    clock.advance(hours=23)
    second = upload(client, b"same-bytes", "renamed.mp3")

    assert second.status_code == 200
    body = second.json()
    assert body["reused"] is True
    assert body["id"] == first["id"]
    assert body["filename"] == "a.wav"
    assert store.list_names(first["id"]) == ["source.wav"]


def test_expired_song_is_not_reused(client, clock):
    first = upload(client, b"same-bytes", "a.wav").json()
    clock.advance(hours=24, seconds=1)
    second = upload(client, b"same-bytes", "a.wav")

    assert second.status_code == 201
    assert second.json()["id"] != first["id"]


def test_different_content_creates_new_song(client):
    a = upload(client, b"one", "a.wav").json()
    b = upload(client, b"two", "b.wav").json()
    assert a["id"] != b["id"]


def test_rejects_oversized_upload_and_leaves_nothing(client, settings):
    too_big = b"0" * (settings.max_upload_bytes + 1)
    response = upload(client, too_big, "big.wav")

    assert response.status_code == 413
    incoming = settings.storage_root / ".incoming"
    assert list(incoming.iterdir()) == []


def test_accepts_upload_exactly_at_limit(client, settings):
    response = upload(client, b"0" * settings.max_upload_bytes, "edge.wav")
    assert response.status_code == 201


def test_rejects_disallowed_extension(client):
    response = upload(client, b"data", "notes.txt")
    assert response.status_code == 415


def test_rejects_file_without_extension(client):
    assert upload(client, b"data", "audio").status_code == 415


def test_rejects_empty_file(client):
    assert upload(client, b"", "empty.wav").status_code == 400


def test_path_in_filename_is_stripped(client, store):
    body = upload(client, b"abc", "../../etc/evil.wav").json()
    assert body["filename"] == "evil.wav"
    assert store.list_names(body["id"]) == ["source.wav"]


def test_song_detail_lists_artifacts_and_expiry(client, store, song):
    detail = client.get(f"/songs/{song['id']}")

    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == song["id"]
    assert body["expires_at"] == song["expires_at"]
    assert body["artifacts"] == {
        "analysis": False,
        "sections": False,
        "sections_edited": False,
        "stems": [],
        "packs": [],
    }

    store.put_bytes(song["id"], "analysis.json", b"{}")
    store.put_bytes(song["id"], "stems/drums.wav", b"wav")
    store.put_bytes(song["id"], "stems/stemset.json", b"{}")
    store.put_bytes(song["id"], "packs/Song One Pack.zip", b"zip")
    artifacts = client.get(f"/songs/{song['id']}").json()["artifacts"]
    assert artifacts["analysis"] is True
    assert [s["name"] for s in artifacts["stems"]] == ["drums.wav"]
    assert [p["name"] for p in artifacts["packs"]] == ["Song One Pack.zip"]
    assert artifacts["packs"][0]["url"].startswith("/files/")


def test_unknown_and_malformed_song_ids_are_404(client):
    assert client.get("/songs/3f2b8a7e-0000-4000-8000-000000000000").status_code == 404
    assert client.get("/songs/not-a-uuid").status_code == 404
    assert client.get("/songs/..%2F..").status_code == 404


def test_expired_song_is_404_everywhere(client, clock, song):
    sid = song["id"]
    clock.advance(hours=24, seconds=1)

    assert client.get(f"/songs/{sid}").status_code == 404
    assert client.get(f"/songs/{sid}/analysis").status_code == 404
    assert client.get(f"/songs/{sid}/sections").status_code == 404
    assert client.post(f"/songs/{sid}/analyze").status_code == 404
    assert client.put(f"/songs/{sid}/sections", json={"sections": []}).status_code == 404


def test_cors_allows_configured_origin(client):
    origin = "http://localhost:3000"
    ok = client.options(
        "/songs",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers["access-control-allow-origin"] == origin
    other = client.options(
        "/songs",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in other.headers
