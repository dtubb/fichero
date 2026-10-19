"""`source.job.review-is-built-from-the-project-and-a-profile` (#5723): the Start estimate prices the review by the
passes it runs, one model call a page for each lens on, and shows each lens's cost per page first, on or off, so a
person can see what turning one on or off costs before Start.

WHY: the estimate priced every cloud run as one call a page; the paleographer review makes one a pass, three with
every lens on, so it showed a third of what it would cost, and turning a lens off changed nothing it said.
"""
from __future__ import annotations

import pytest

from fichero_server.recipes.start import estimate
from fichero_server.workflows import model_comparison

REVIEW = {"workflow": "Paleographer Review", "steps": ["correct"], "job": "correct", "runs_on": "cloud:openai",
          "provider_override": "openai", "model_override": "gpt-5"}


@pytest.fixture(autouse=True)
def a_cent_a_call(monkeypatch):
    """One model call (1,200 tokens in) costs a cent."""
    monkeypatch.setattr(model_comparison, "estimate_cost", lambda model, tokens_in, tokens_out, provider="":
                        round(tokens_in / 1200 * 0.01, 6))


def test_every_lens_on_is_three_calls_a_page():
    [row] = estimate([REVIEW], 10)["runs"]
    assert row["calls_per_page"] == 3 and row["cost_usd"] == pytest.approx(0.30)


def test_a_lens_off_is_a_call_a_page_less():
    [row] = estimate([{**REVIEW, "lenses": ["abbreviations", "names-and-dates"]}], 10)["runs"]
    assert row["calls_per_page"] == 2 and row["cost_usd"] == pytest.approx(0.20)


def test_each_lens_says_its_cost_per_page_on_or_off():
    [row] = estimate([{**REVIEW, "lenses": ["orthography"]}], 10)["runs"]
    assert row["lenses"] == [
        {"lens": "abbreviations", "on": False, "cost_per_page_usd": pytest.approx(0.01)},
        {"lens": "orthography", "on": True, "cost_per_page_usd": pytest.approx(0.01)},
        {"lens": "names-and-dates", "on": False, "cost_per_page_usd": pytest.approx(0.01)}]


def test_a_review_on_this_mac_costs_nothing_a_lens_and_any_other_run_is_one_call():
    [here] = estimate([{**REVIEW, "runs_on": "this-mac", "provider_override": "omlx"}], 10)["runs"]
    assert here["cost_usd"] == 0.0 and {lens["cost_per_page_usd"] for lens in here["lenses"]} == {0.0}
    [read] = estimate([{**REVIEW, "job": "read-a-line", "steps": ["read"]}], 10)["runs"]
    assert read["calls_per_page"] == 1 and read["lenses"] == [] and read["cost_usd"] == pytest.approx(0.10)
