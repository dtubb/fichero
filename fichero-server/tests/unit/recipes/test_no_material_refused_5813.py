"""#5813: `source.onboard.your-material-waits`. No material, no plan and no Start: the engine refuses in words.

WHY: the owner (2026-10-19) ruled Set Up's Continue waits for material; the engine holds the same rule, so a client
that skips the footer is refused too. A test that assembles gets material from the `with_material` fixture.
"""
from __future__ import annotations

from fichero_server.api.routes.system.recipes import NO_MATERIAL, NO_MATERIAL_TO_PLAN

ANSWERS = {"purpose": "search", "languages": ["es"], "scripts": ["Latn"], "pages": 10, "mac_memory_gb": 16}


def test_assemble_on_an_empty_project_is_refused_in_words(client):
    r = client.post("/api/recipes/assemble", json=ANSWERS)
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == NO_MATERIAL_TO_PLAN


def test_start_on_an_empty_project_is_refused_in_words(client):
    r = client.post("/api/recipes/project/start")
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == NO_MATERIAL


def test_assemble_with_material_is_not_refused(client, with_material):
    assert client.post("/api/recipes/assemble", json=ANSWERS).status_code == 200
