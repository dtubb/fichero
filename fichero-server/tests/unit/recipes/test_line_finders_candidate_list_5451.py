"""`source.recipe.line-finders-are-a-candidate-list` (#5451, ruled 2026-10-17): the Find lines route is a list.

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY: "hand" is not fixed to Kraken: a hand
may go to Kraken, a cloud model or an MLX model, A/B'd by the bake-off, and the recipe also looks online. So the line
finders the bake-off compares come from the cards that name the Find lines job, and the planner skips a pin it has no
workflow for, naming it, instead of running Kraken in its place.
"""
from __future__ import annotations

from fichero_server.recipes import bakeoff
from fichero_server.recipes.assemble import Card
from fichero_server.recipes.cards import seed_cards
from fichero_server.recipes.start import plan_start


def test_every_card_naming_find_lines_is_a_candidate_line_finder():
    """source.recipe.line-finders-are-a-candidate-list: "every card naming `find-lines` is a bake-off candidate"."""
    named = {c.id for c in seed_cards() if "find-lines" in c.jobs}
    assert named and named <= {f["card"] for f in bakeoff.line_finders()}, named


def test_a_new_line_finder_card_is_listed_and_never_run_as_kraken(monkeypatch):
    """source.recipe.line-finders-are-a-candidate-list: a card with no workflow is a candidate listed as not scored,
    saying why; adding a card adds a candidate."""
    cloud = Card(id="cloud:google/gemini-lines@2026", pin={"cloud": "google", "model": "gemini-lines"},
                 jobs=frozenset({"find-lines"}), scripts=None, languages=None, material=frozenset({"handwriting"}),
                 runs_on="cloud:google")
    monkeypatch.setattr(bakeoff, "seed_cards", lambda: (*seed_cards(), cloud), raising=False)

    listed = {f["card"]: f for f in bakeoff.line_finders()}

    assert cloud.id in listed and listed[cloud.id]["not_available"], listed.get(cloud.id)
    assert bakeoff._finder_unavailable(listed[cloud.id]) == listed[cloud.id]["not_available"]


def test_the_planner_skips_a_line_finder_it_has_no_workflow_for_by_name():
    """source.recipe.line-finders-are-a-candidate-list: a pin with no workflow is skipped saying so, never Kraken."""
    step = {"id": "lines", "job": "find-lines", "model": {"cloud": "google", "model": "gemini-lines"},
            "runs_on": "cloud:google"}
    plan = plan_start({"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t", "steps": [step]},
                      stays_local=False)

    assert plan["runs"] == [] and "gemini-lines" in plan["skipped"][0]["why"], plan
