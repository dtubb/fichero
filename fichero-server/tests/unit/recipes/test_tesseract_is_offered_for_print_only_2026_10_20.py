"""`source.recipe.reader-tiers`: Tesseract is offered for print and typescript only, never for handwriting, in the
rules, the bake-off and the candidate list a person chooses from."""
from __future__ import annotations

TESSERACT = "tesseract:tessdata/spa@unpinned"


def _listed(client, material):
    r = client.get("/api/recipes/candidates", params={"scripts": "Latn", "languages": "es", "material": material,
                                                      "job": "read-a-line"})
    assert r.status_code == 200, r.text
    return {c["id"]: c for c in r.json()["items"]}


def test_for_print_it_is_named_and_says_it_cannot_run_yet(client):
    card = _listed(client, "print")[TESSERACT]
    assert card["rule_rank"] is None and "cannot run it yet" in card["refused"]
    assert "baseline" in card["offered_because"]


def test_for_typescript_too(client):
    assert TESSERACT in _listed(client, "typescript")


def test_for_handwriting_it_is_not_offered_at_all(client):
    assert TESSERACT not in _listed(client, "handwriting")
