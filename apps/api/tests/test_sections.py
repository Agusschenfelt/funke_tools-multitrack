SECTIONS = {
    "source": "Song One.wav",
    "sections": [
        {"name": "intro", "start": 0.0},
        {"name": "verse", "start": 12.5, "label": "Verse 1", "confidence": 0.8, "cluster": 1},
        {"name": "chorus", "start": 40.0},
    ],
}


def seed(store, song_id, payload=SECTIONS):
    import json

    store.put_bytes(song_id, "sections.json", json.dumps(payload).encode())


def test_get_sections_missing_is_404(client, song):
    assert client.get(f"/songs/{song['id']}/sections").status_code == 404


def test_get_sections_returns_detected_not_edited(client, store, song):
    seed(store, song["id"])
    body = client.get(f"/songs/{song['id']}/sections").json()

    assert body["edited"] is False
    assert body["updated_at"] is None
    assert [s["name"] for s in body["sections"]] == ["intro", "verse", "chorus"]
    assert body["sections"][1]["confidence"] == 0.8


def test_put_sections_writes_file_and_sets_edited(client, store, song):
    seed(store, song["id"])
    edited = {
        "sections": [
            {"name": "intro", "start": 0},
            {"name": "bridge", "start": 30.25, "label": "Puente"},
        ]
    }
    put = client.put(f"/songs/{song['id']}/sections", json=edited)

    assert put.status_code == 200
    assert put.json()["edited"] is True
    got = client.get(f"/songs/{song['id']}/sections").json()
    assert got["edited"] is True
    assert got["updated_at"] is not None
    assert [s["name"] for s in got["sections"]] == ["intro", "bridge"]
    assert b'"bridge"' in store.get_bytes(song["id"], "sections.json")
    detail = client.get(f"/songs/{song['id']}").json()
    assert detail["artifacts"]["sections"] is True
    assert detail["artifacts"]["sections_edited"] is True


def test_put_sections_without_prior_detection_creates_file(client, store, song):
    response = client.put(
        f"/songs/{song['id']}/sections", json={"sections": [{"name": "verse", "start": 1.0}]}
    )
    assert response.status_code == 200
    assert store.exists(song["id"], "sections.json")


def test_put_rejects_unsorted_sections(client, store, song):
    seed(store, song["id"])
    bad = {"sections": [{"name": "verse", "start": 10}, {"name": "intro", "start": 0}]}
    response = client.put(f"/songs/{song['id']}/sections", json=bad)

    assert response.status_code == 422
    assert client.get(f"/songs/{song['id']}/sections").json()["edited"] is False


def test_put_rejects_duplicate_starts(client, song):
    bad = {"sections": [{"name": "verse", "start": 10}, {"name": "chorus", "start": 10}]}
    assert client.put(f"/songs/{song['id']}/sections", json=bad).status_code == 422


def test_put_rejects_unknown_name_and_negative_start(client, song):
    unknown = {"sections": [{"name": "drop", "start": 1}]}
    negative = {"sections": [{"name": "verse", "start": -1}]}
    assert client.put(f"/songs/{song['id']}/sections", json=unknown).status_code == 422
    assert client.put(f"/songs/{song['id']}/sections", json=negative).status_code == 422


def test_second_edit_keeps_flag_and_updates_timestamp(client, clock, song):
    url = f"/songs/{song['id']}/sections"
    first = client.put(url, json={"sections": [{"name": "intro", "start": 0}]}).json()
    clock.advance(minutes=5)
    second = client.put(url, json={"sections": [{"name": "verse", "start": 3}]}).json()

    assert second["edited"] is True
    assert second["updated_at"] > first["updated_at"]


def test_get_analysis(client, store, song):
    assert client.get(f"/songs/{song['id']}/analysis").status_code == 404
    store.put_bytes(song["id"], "analysis.json", b'{"source": "x", "duration": 1.0}')
    response = client.get(f"/songs/{song['id']}/analysis")
    assert response.status_code == 200
    assert response.json()["duration"] == 1.0
