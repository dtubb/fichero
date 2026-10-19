"""#5516 (R1 live): a Fraktur (Latf) project got "no model fits read-a-line". Latin-script readers state Latn, never
Latf; a script's parent is a related script (`_PARENT`), so a reader that states the parent and lists the language fits
(`source.recipe.no-cross-script-reader`: Fraktur is Latin, not another script). Shipped cards only, through the route."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _shipped_cards_only(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")


@pytest.mark.parametrize("material", ["print", "handwriting"])
def test_a_fraktur_project_gets_a_reader_not_a_gap(client, with_material, material):
    body = {"purposes": ["transcribe"], "languages": ["de"], "scripts": ["Latf"], "materials": [material],
            "mac_memory_gb": 32}
    r = client.post("/api/recipes/assemble", json=body)
    assert r.status_code == 200, r.text
    read = next(s for s in r.json()["steps"] if s["job"] == "read-a-line")
    assert read.get("model"), read.get("gap")
