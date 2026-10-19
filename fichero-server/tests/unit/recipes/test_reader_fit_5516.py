"""The rules rank a reader by its fit before a card's own average (#5516), tested to the spec:
`source.recipe.script-reader-first` and `source.recipe.no-cross-script-reader`
(docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: the corpus run of 2026-10-06 gave medieval Latin and Czech textura PP-OCRv6 (a 3.9% CER averaged over 44
languages) over CATMuS Medieval, the obvious fit, which then won the bake-off (11.2% against 16.4%); and German
Fraktur got no reader at all. Only the shipped cards here (an empty model store, offline), through the route the app
calls (`POST /api/recipes/assemble`).
"""

from __future__ import annotations

import pytest

PP_OCR = {"zenodo": "10.5281/zenodo.21788410"}
MCCATMUS = {"zenodo": "10.5281/zenodo.13788177"}
CATMUS_MEDIEVAL = {"zenodo": "10.5281/zenodo.12743230"}


@pytest.fixture(autouse=True)
def _shipped_cards_only(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")


def _reader(client, languages, scripts, material="handwriting", period=None) -> dict:
    body = {"purposes": ["transcribe"], "languages": languages, "scripts": scripts, "materials": [material],
            "mac_memory_gb": 32}
    if period:
        body["period"] = period
    r = client.post("/api/recipes/assemble", json=body)
    assert r.status_code == 200, r.text
    return next(s for s in r.json()["steps"] if s["job"] == "read-a-line")


def test_a_medieval_project_gets_catmus_medieval_over_an_averaged_cer(client, with_material):
    """"a card whose period covers the project's period … comes before one that states no period … So a
    13th-century Latin project gets CATMuS Medieval over PP-OCRv6's 3.9% averaged over 44 languages". The run's
    Czech textura: no card made for Czech, so before this the averaged CER won."""
    assert _reader(client, ["cs"], ["Latn"], period="15th century")["model"] == CATMUS_MEDIEVAL


def test_a_project_that_answers_no_period_ranks_as_before(client, with_material):
    """"A project that answers no period ranks as before": Spanish keeps PP-OCRv6."""
    assert _reader(client, ["es"], ["Latn"])["model"] == PP_OCR


def test_an_early_modern_project_gets_the_reader_of_its_period(client, with_material):
    assert _reader(client, ["es"], ["Latn"], period="1702")["model"] == MCCATMUS


def test_a_german_print_set_to_latin_gets_the_reader_of_its_period(client, with_material):
    """"a 19th-century German print set to Latin gets McCATMuS" (the run: NZZ Fraktur set to Latn got PP-OCRv6)."""
    assert _reader(client, ["de"], ["Latn"], material="print", period="19th century")["model"] == MCCATMUS
