"""`source.recipe.period-weighs-in-the-reader-rank` (#5683).

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY (2026-10-11, the MCP onboarding walk):
a project saved as 16th century, Popayán ranked McCATMuS (16th–21st c., installed) 4th for read-a-line, behind
COMMA (medieval Latin, a 1.7 GB download) and CATMuS Medieval; Apple Vision was missing from the line step's
candidates though the bake-off counts it; and next_run listed a research-licence model to be read with. Through
the routes with the shipped cards; only this Mac's stores are stubbed.
"""
from __future__ import annotations

from fichero_server.recipes.assemble import Answers, in_period
from fichero_server.recipes.cards import all_seed_cards
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)

MCCATMUS = "kraken:zenodo/10.5281/zenodo.13788177@unpinned"
CATMUS_MEDIEVAL = "kraken:zenodo/10.5281/zenodo.12743230@unpinned"
APPLE = "apple:vision/recognize-text@os"


def _candidates(client, **params):
    r = client.get("/api/recipes/candidates", params={"job": "read-a-line", "scripts": "Latn", "languages": "es",
                                                       **params})
    assert r.status_code == 200, r.text
    return {i["id"]: i for i in r.json()["items"]}


def test_a_reader_made_for_the_period_ranks_first(client, mac):
    sixteenth = _candidates(client, period="16th century")
    assert sixteenth[MCCATMUS]["rule_rank"] == 1, sorted((v["rule_rank"] or 99, k) for k, v in sixteenth.items())
    twelfth = _candidates(client, period="12th century")
    # Ruled 2026-10-17: another period only lowers the rank, so McCATMuS keeps one, below the medieval reader.
    assert twelfth[CATMUS_MEDIEVAL]["rule_rank"] is not None
    assert twelfth[MCCATMUS]["rule_rank"] > twelfth[CATMUS_MEDIEVAL]["rule_rank"]


def test_the_recipe_reads_the_saved_period(client, with_material, mac):
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
               "mac_memory_gb": 32, "period": "16th century", "place": "Popayán"}
    r = client.post("/api/recipes/assemble", json=answers)
    assert r.status_code == 200, r.text
    read = next(s for s in r.json()["steps"] if s["job"] == "read-a-line")
    assert read["card"]["id"] == MCCATMUS, read
    assert any("period" in reason for reason in read["reasons"]), read["reasons"]


def test_apple_vision_is_offered_for_the_line_step_without_a_rule_rank(client, mac):
    apple = _candidates(client)[APPLE]
    assert apple["rule_rank"] is None and apple["in_recipe_rules"] is False


def test_the_cards_state_their_period():
    cards = {c.id: c for c in all_seed_cards()}
    a = Answers(period="16th century")
    assert in_period(cards[MCCATMUS], a) is True and in_period(cards[CATMUS_MEDIEVAL], a) is True
    assert in_period(cards[CATMUS_MEDIEVAL], Answers(period="1650–1700")) is False


def test_a_licence_not_accepted_is_named_not_scored():
    from dataclasses import replace

    from fichero_server.recipes.bakeoff import _not_scored_because

    (qwen3b,) = [c for c in all_seed_cards() if "Qwen2.5-VL-3B" in c.id]
    why = _not_scored_because(replace(qwen3b, open_licence=False), "vision", "m", "omlx")
    assert why and "accept" in why
