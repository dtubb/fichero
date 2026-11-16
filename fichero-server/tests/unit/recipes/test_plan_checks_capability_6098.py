"""`ai.cloud.plan-checks-the-capability` (#6098): a step whose cloud model lacks what its job needs is skipped at plan time with
`choose-model`, so no Read fails at validation for it."""
from __future__ import annotations

import pytest

from fichero_server import llm
from fichero_server.recipes.start import capability_gap, plan_start
from tests.unit.recipes.test_start_plan import CLOUD_CORRECT, LINES, READ, _recipe


def _caps(monkeypatch, answer):
    monkeypatch.setattr(llm, "_model_has_capability", lambda provider, model, needed: answer)


def test_a_text_only_model_cannot_read_page_images(monkeypatch):
    _caps(monkeypatch, False)
    why = capability_gap(CLOUD_CORRECT, CLOUD_CORRECT["job"])
    assert why and "cannot" in why and "choose another model" in why


def test_the_plan_skips_the_step_with_choose_model(monkeypatch):
    _caps(monkeypatch, False)
    plan = plan_start(_recipe(LINES, READ, CLOUD_CORRECT), stays_local=False)
    skipped = {s["step"]: s for s in plan["skipped"]}
    assert skipped["correct"]["fix"] == "choose-model" and "cannot" in skipped["correct"]["why"]
    assert all("correct" not in run["steps"] for run in plan["runs"])


@pytest.mark.parametrize("answer", [True, None])
def test_a_capable_or_unknown_model_is_planned(monkeypatch, answer):
    _caps(monkeypatch, answer)  # None: the engine does not know, so the step is not blocked
    assert capability_gap(CLOUD_CORRECT, CLOUD_CORRECT["job"]) is None
    plan = plan_start(_recipe(LINES, READ, CLOUD_CORRECT), stays_local=False)
    assert not [s for s in plan["skipped"] if s["step"] == "correct" and "cannot" in s["why"]]


def test_a_text_job_asks_for_text(monkeypatch):
    asked = []
    monkeypatch.setattr(llm, "_model_has_capability", lambda provider, model, needed: asked.append(needed) or True)
    capability_gap({**CLOUD_CORRECT, "job": "find-statements"}, "find-statements")
    capability_gap(CLOUD_CORRECT, CLOUD_CORRECT["job"])
    assert asked == ["text", "vision"]
