"""`source.recipe.missing-key-never-substitutes` (#5364): a cloud step whose provider has no key waits.

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY: a step pinned to a cloud model
whose key is missing used to plan as runnable and die mid-run; or, worse, a nearby model could be put in its
place. Start skips the step, says "Needs a key for <provider>", and runs no other model for it. The other steps
still run. Through `plan_start` with the key lookup stubbed.
"""
from __future__ import annotations

from fichero_server.recipes import start
from fichero_server.recipes.start import plan_start
from tests.unit.recipes.test_start_plan import CLOUD_CORRECT, LINES, READ, _recipe


def test_a_cloud_step_with_no_key_waits_and_nothing_takes_its_place(monkeypatch):
    """source.recipe.missing-key-never-substitutes: waits with "Needs a key for <provider>"; no other model runs."""
    monkeypatch.setattr(start, "provider_without_key", lambda step: "OpenAI" if step.get("id") == "correct" else None)

    plan = plan_start(_recipe(LINES, READ, CLOUD_CORRECT), stays_local=False)

    skipped = {s["step"]: s for s in plan["skipped"]}
    assert "Needs a key for OpenAI" in skipped["correct"]["why"], plan["skipped"]
    assert all("correct" not in run["steps"] for run in plan["runs"]), "no model is run in the keyless step's place"
    assert any("read" in run["steps"] for run in plan["runs"]), "the other steps still run"


def test_a_cloud_step_with_its_key_is_planned(monkeypatch):
    monkeypatch.setattr(start, "provider_without_key", lambda step: None)

    plan = plan_start(_recipe(LINES, READ, CLOUD_CORRECT), stays_local=False)

    assert not [s for s in plan["skipped"] if s["step"] == "correct"], plan["skipped"]
