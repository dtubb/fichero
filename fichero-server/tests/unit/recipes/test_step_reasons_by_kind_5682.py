"""`source.onboard.deterministic-recipe` (#5682): each step's reasons are its own kind's.

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY (2026-10-11, the MCP onboarding walk):
the embedder, spaCy and blla each said "made for handwriting" and "unmeasured on your pages until a bake-off
measures it", reasons only a reader has; blla's card for finding regions called it "Kraken's built-in line finder".
Through the assemble route with the shipped cards.
"""
from __future__ import annotations

ANSWERS = {"purposes": ["transcribe", "map-places", "search"], "languages": ["es"], "scripts": ["Latn"],
           "materials": ["handwriting"], "mac_memory_gb": 32}
READERS = {"read-a-line", "read-a-page"}


def test_only_a_reader_speaks_of_material_cer_and_bake_offs(client, with_material):
    r = client.post("/api/recipes/assemble", json=ANSWERS)
    assert r.status_code == 200, r.text
    steps = {s["job"]: s for s in r.json()["steps"] if s.get("reasons")}
    assert READERS & set(steps), steps.keys()
    for job, step in steps.items():
        said = " ".join(step["reasons"])
        if job in READERS:
            assert "bake-off" in said, step["reasons"]
        else:
            assert "bake-off" not in said and "made for handwriting" not in said and "CER" not in said, (job, said)
    assert {"find-lines", "find-names-tag-words", "make-a-vector"} <= set(steps)


def test_blla_is_named_for_lines_and_regions():
    from fichero_server.recipes.cards import all_seed_cards

    (blla,) = [c for c in all_seed_cards() if c.pin.get("kraken") == "blla"]
    assert "region" in blla.note and "find-regions" in blla.jobs
