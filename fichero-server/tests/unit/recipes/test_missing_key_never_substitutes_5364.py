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
    # The app has no Add Key button yet: the fix is said in the why, and `fix` is no token the app would not know.
    assert "Add Key" in skipped["correct"]["why"] and skipped["correct"]["fix"] is None, skipped["correct"]
    assert all("correct" not in run["steps"] for run in plan["runs"]), "no model is run in the keyless step's place"
    assert any("read" in run["steps"] for run in plan["runs"]), "the other steps still run"


def test_a_cloud_step_with_its_key_is_planned(monkeypatch):
    monkeypatch.setattr(start, "provider_without_key", lambda step: None)

    plan = plan_start(_recipe(LINES, READ, CLOUD_CORRECT), stays_local=False)

    assert not [s for s in plan["skipped"] if s["step"] == "correct"], plan["skipped"]


def _keys(monkeypatch, key):
    """The real lookup (provider info, then `get_api_key`) with only the keychain-and-environment read stubbed."""
    from fichero_server import llm

    llm.clear_api_key_cache()
    monkeypatch.setattr(llm, "_read_api_key_uncached", lambda provider: key)
    return llm


def test_the_real_lookup_names_the_provider_of_a_cloud_pin_with_no_key(monkeypatch):
    """source.recipe.missing-key-never-substitutes: through the provider table, not a stub of `provider_without_key`."""
    llm = _keys(monkeypatch, None)
    try:
        assert start.provider_without_key(CLOUD_CORRECT) == "OpenAI"
        _keys(monkeypatch, "sk-test")
        assert start.provider_without_key(CLOUD_CORRECT) is None, "a configured key lets the step run"
        _keys(monkeypatch, None)
        assert start.provider_without_key(LINES) is None, "a local pin needs no key"
        assert start.provider_without_key({**CLOUD_CORRECT, "model": {"cloud": "no-such-provider", "model": "x"}}) is None
    finally:
        llm.clear_api_key_cache()
