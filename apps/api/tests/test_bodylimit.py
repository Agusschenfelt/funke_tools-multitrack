import json
from dataclasses import replace

from alembic import command
from conftest import alembic_config, upload
from fastapi.testclient import TestClient

from api.bodylimit import MAX_JSON_BODY_BYTES
from api.main import create_app

OVERSIZED = b"[" + b"0," * MAX_JSON_BODY_BYTES + b"0]"


def test_oversized_content_length_is_413_on_sections(client, song):
    response = client.put(
        f"/songs/{song['id']}/sections",
        content=OVERSIZED,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


def test_oversized_chunked_body_without_content_length_is_413(client, song):
    def chunks():
        for _ in range(MAX_JSON_BODY_BYTES // 1024 + 2):
            yield b" " * 1024

    response = client.put(
        f"/songs/{song['id']}/sections",
        content=chunks(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


def test_oversized_body_is_413_on_job_routes_even_for_unknown_song(client):
    unknown = "00000000-0000-4000-8000-000000000000"
    for route in ("analyze", "separate", "stagepack"):
        response = client.post(
            f"/songs/{unknown}/{route}",
            content=OVERSIZED,
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 413, route


def test_normal_sections_body_is_accepted(client, song):
    body = {"source": "x", "sections": [{"name": "intro", "start": 0.0}]}
    response = client.put(f"/songs/{song['id']}/sections", json=body)
    assert response.status_code == 200
    assert len(json.dumps(body)) < MAX_JSON_BODY_BYTES


def test_upload_keeps_its_own_larger_limit(settings, queue, clock):
    bigger = replace(settings, max_upload_mb=3)
    command.upgrade(alembic_config(bigger.database_url), "head")
    with TestClient(create_app(bigger, queue=queue, clock=clock)) as client:
        ok = upload(client, content=b"a" * (2 * 1024 * 1024))
        too_big = upload(client, content=b"b" * (3 * 1024 * 1024 + 1))
    assert ok.status_code == 201
    assert too_big.status_code == 413
    assert "MB limit" in too_big.json()["detail"]
