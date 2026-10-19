"""Find where the readers disagree needs no model of its own (#5812).

Spec: `source.disagree.built-in-with-two-readers` and `source.disagree.one-reader-says-which-to-add`
(docs/contributor_manual/specs/source/readings-and-apparatus.md). WHY: on Set Up > Ready the step said "No model on this
Mac does this yet" and sent the person to a text-model search for a step that only compares readers.
"""

from __future__ import annotations

from fichero_server.recipes.start import DISAGREE_JOB, plan_start
from tests.unit.recipes.test_installed_model_first_to_spec import LINES, SEVEN, mac  # noqa: F401 (fixture)

KRAKEN = {"zenodo": "10.5281/zenodo.13788177"}
KRAKEN_READS = {"id": "read", "job": "read-a-line", "model": KRAKEN}
CORRECT = {"id": "correct", "job": "correct", "model": SEVEN, "runs_on": "this-mac"}
DOUBT = {"id": "doubt", "job": DISAGREE_JOB}


def _recipe(*steps):
    return {"fichero_recipe": 1, "id": "t/disagree", "version": "0.1.0", "title": "t", "steps": list(steps)}


def test_a_plan_with_two_readers_has_no_run_for_the_step_and_says_when_it_is_worked_out(mac):
    plan = plan_start(_recipe(LINES, KRAKEN_READS, CORRECT, DOUBT), stays_local=True)

    assert not [r for r in plan["runs"] if r["job"] == DISAGREE_JOB], "nothing runs and nothing is stored (#5816)"
    (said,) = [s for s in plan["skipped"] if s["step"] == "doubt"]
    assert "worked out when you open a page" in said["why"] and said["fix"] is None
    assert not [s for s in plan["skipped"] if "off this Mac" in s["why"] or "has no model" in s["why"]]


def test_a_step_that_names_its_own_model_is_still_sampled(mac):
    step = {**DOUBT, "model": SEVEN}
    plan = plan_start(_recipe(LINES, KRAKEN_READS, CORRECT, step), stays_local=True)

    sampled = [r for r in plan["runs"] if r["job"] == DISAGREE_JOB]
    assert len(sampled) == 5 and all(r["card"] == "workflow" for r in sampled)


def test_one_reader_that_cannot_be_sampled_says_which_reader_to_add_and_offers_no_model(mac):
    plan = plan_start(_recipe(LINES, KRAKEN_READS, DOUBT), stays_local=True)

    (skipped,) = [s for s in plan["skipped"] if s["step"] == "doubt"]
    assert "add a second reader" in skipped["why"]
    assert skipped["fix"] is None, "no Choose a model for a step that needs none"
    assert not plan.get("needs_a_model")


def test_the_finder_for_a_sampled_reader_offers_vision_readers_never_a_text_search(monkeypatch):
    """`source.disagree.one-reader-says-which-to-add`: the chooser for a step that samples one reader is the readers'
    finder kept to models the plan can sample, and its sources are the readers' (no 'No online search for this step')."""
    from types import SimpleNamespace

    from fichero_server.recipes import discovery

    sampleable = SimpleNamespace(pin={"cloud": "anthropic", "model": "claude-sonnet"})
    kraken = SimpleNamespace(pin={"zenodo": "10.5281/zenodo.13788177"})
    asked = {}

    def readers(a, *, online, search=None, not_searched=None, job="read-a-line"):
        asked["job"] = job
        return [sampleable, kraken], [{"source": "hugging-face", "state": "cached", "count": 0, "detail": "x"}]

    real = discovery.discover
    monkeypatch.setattr(discovery, "discover", lambda *a, **k: real(*a, **k) if k.get("job") == "find-where-readers-disagree" else readers(*a, **k))
    cards, sources = discovery.discover(SimpleNamespace(), online=False, job="find-where-readers-disagree")

    assert asked["job"] == "read-a-line"
    assert cards == [sampleable], "Kraken cannot be sampled as a vision model"
    assert not [s for s in sources if s["detail"] == discovery.NO_STEP_SEARCH]
