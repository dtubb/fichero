"""`source.onboard.correct-off-unless-a-corrector-is-here`, ruled Q3 2026-10-17 (#5677): with no corrector on this Mac,
Correct is off; where a cloud corrector's provider has a key set, Correct is OFFERED at Ready with its cost for the
project's pages, never turned on by itself; with no key, no cloud is named.

WHY: the off line named a cloud price whether or not the person could use that cloud, and nothing offered it.
"""
from __future__ import annotations

from fichero_server.recipes.assemble import Answers, Card, _correct_left_off

MLX = Card(id="mlx:hf/x/Qwen2.5-VL-7B@1", pin={"hf": "x/Qwen2.5-VL-7B"}, jobs=frozenset({"correct"}), scripts=None,
           languages=None, material=frozenset({"handwriting"}), size_gb=5.7, memory_gb=8, installed=False)
CLOUD = Card(id="cloud:anthropic/claude@1", pin={"provider": "anthropic"}, jobs=frozenset({"correct"}), scripts=None,
             languages=frozenset({"es"}), material=frozenset({"handwriting"}), runs_on="cloud:anthropic", cost_per_page=0.02,
             note="Claude")
A = dict(purposes=("transcribe",), materials=("handwriting",), languages=frozenset({"es"}), pages=500,
         mac_memory_gb=32)


def test_correct_offered_with_a_key_5677():
    off = _correct_left_off([MLX, CLOUD], Answers(**A, cloud_keys=("anthropic",)))
    assert off is not None and off["job"] == "correct"  # never on by itself
    offer = off["offered"]
    # Three review passes a page (every lens on), each one call at the card's $0.02 (#5723).
    assert offer["runs_on"] == "anthropic" and offer["pages"] == 500 and offer["calls_per_page"] == 3
    assert offer["cost_usd"] == 30.0 and "$30.00" in off["sentence"]


def test_the_offer_prices_only_the_lenses_turned_on_5677():
    a = Answers(**A, cloud_keys=("anthropic",), job_answers={"review_lenses": ["names-and-dates"]})
    offer = _correct_left_off([MLX, CLOUD], a)["offered"]
    assert offer["calls_per_page"] == 1 and offer["cost_usd"] == 10.0


def test_with_no_key_no_cloud_is_offered_or_priced_5677():
    off = _correct_left_off([MLX, CLOUD], Answers(**A))
    assert off is not None and off.get("offered") is None and "$" not in off["sentence"]


def test_the_persons_cloud_reader_is_offered_as_the_corrector_and_priced_5677(monkeypatch):
    """The offer must reach a live project: no shipped or installed card does Correct in the cloud, so a keyed
    cloud vision reader from the person's settings is offered as the corrector, priced from the price list, and
    never chosen by the rules (it is not among their cards)."""
    from fichero_server.api.routes.system import recipes as route
    from fichero_server.recipes import bakeoff
    from fichero_server.recipes.assemble import assemble

    remote = Card(id="anthropic:claude-sonnet-4-5@row1", pin={"cloud": "anthropic", "model": "claude-sonnet-4-5"},
                  jobs=frozenset({"read-a-line", "read-a-page"}), scripts=None, languages=None, material=frozenset(),
                  runs_on="cloud:anthropic", note="Claude Sonnet (Anthropic)", offered_only=True)
    monkeypatch.setattr(bakeoff, "cloud_readers", lambda: [remote])
    (corrector,) = route._cloud_correctors(("anthropic",))
    assert "correct" in corrector.jobs and corrector.cost_per_page > 0
    a = Answers(**A, cloud_keys=("anthropic",))
    recipe = assemble(a, [MLX], offered=[corrector])
    (off,) = [o for o in recipe["left_off"] if o["job"] == "correct"]
    assert off["offered"]["card"] == remote.id and off["offered"]["cost_usd"] > 0
    assert "does not list es" in off["sentence"]  # its languages are not known: said, never assumed
    assert route._cloud_correctors(()) == []  # no key, no cloud named


def test_the_offered_corrector_is_taken_by_use_candidate_5677(client, db, monkeypatch):
    """Ready's press: the Correct step takes the offered card through use-candidate, as the person's choice."""
    from tests.unit.recipes.test_recipe_execution_to_spec import _recipe, _save

    from fichero_server.api.routes.system import recipes as route
    from fichero_server.recipes import bakeoff

    remote = Card(id="anthropic:claude-sonnet-4-5@row1", pin={"cloud": "anthropic", "model": "claude-sonnet-4-5"},
                  jobs=frozenset({"read-a-line"}), scripts=None, languages=None, material=frozenset(),
                  runs_on="cloud:anthropic", note="Claude Sonnet (Anthropic)", offered_only=True)
    monkeypatch.setattr(bakeoff, "cloud_readers", lambda: [remote])
    monkeypatch.setattr(route, "_providers_with_keys", lambda: ["anthropic"])
    _save(client, _recipe(None, {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}},
                          {"id": "correct", "job": "correct", "model": {"hf": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
                                                                       "revision": "main"}}))
    used = client.post("/api/recipes/project/steps/use-candidate", json={"step": "correct", "card": remote.id})
    assert used.status_code == 200, used.text
    step = next(s for s in used.json()["recipe"]["steps"] if s["id"] == "correct")
    assert step["model"] == remote.pin
