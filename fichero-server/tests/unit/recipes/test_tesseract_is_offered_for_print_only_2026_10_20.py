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


def test_only_where_its_data_covers_the_language_and_script(client):
    r = client.get("/api/recipes/candidates", params={"scripts": "Latf", "languages": "de", "material": "print",
                                                      "job": "read-a-line", "mac_memory_gb": 32})
    assert TESSERACT not in {c["id"] for c in r.json()["items"]}  # Spanish data, not German in Fraktur


def test_each_reading_candidate_names_its_tier(client):
    r = client.get("/api/recipes/candidates", params={"scripts": "Latn", "languages": "es", "material": "handwriting",
                                                      "job": "read-a-line", "mac_memory_gb": 32})
    tiers = {c["id"]: (c["tier"], c["tier_words"]) for c in r.json()["items"]}
    assert tiers["kraken:zenodo/10.5281/zenodo.21788410@unpinned"] == ("specialist", "Specialist line reader")
    assert tiers["apple:vision/read@os"][0] == "general" if "apple:vision/read@os" in tiers else True
    small = [t for i, t in tiers.items() if i.startswith("mlx:") and "3b" in i.lower()]
    assert all(t[0] == "small-vlm" for t in small)
    names = client.get("/api/recipes/candidates", params={"scripts": "Latn", "job": "find-regions"}).json()["items"]
    assert all(c["tier"] is None for c in names)  # another job has no reader tier
