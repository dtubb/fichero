"""`source.recipe.kraken-then-cloud-unsure-lines`: the cost of variant A is shown BEFORE the run, from the most lines it
can send (Kraken has not read anything yet), with the bar and the basis in words; any other run says none of this (#5894)."""
from __future__ import annotations

import pytest

from fichero_server.recipes.start import ASSUMED_LINES_PER_PAGE, LINE_TOKENS_IN, estimate
from fichero_server.workflows import model_comparison

CORRECT = {"workflow": "Paleographer Review", "steps": ["correct"], "job": "correct", "runs_on": "cloud:anthropic",
           "provider_override": "anthropic", "model_override": "claude-x"}
A = {**CORRECT, "tool_config": {"transcribe_review": {"only_below_confidence": 0.6}}}


@pytest.fixture(autouse=True)
def a_cent_per_1200_tokens(monkeypatch):
    monkeypatch.setattr(model_comparison, "estimate_cost", lambda model, tokens_in, tokens_out, provider="":
                        round(tokens_in / 1200 * 0.01, 6))


def test_variant_a_is_priced_from_the_most_lines_it_can_send_and_says_so():
    [row] = estimate([A], 10)["runs"]
    most = 10 * ASSUMED_LINES_PER_PAGE
    assert row["certainty_bar"] == 0.6 and row["lines_at_most"] == most
    assert row["cost_usd"] == pytest.approx(most * LINE_TOKENS_IN / 1200 * 0.01)
    assert f"at most {most} lines" in row["lines_basis"] and "under 0.6 sure" in row["lines_basis"]
    assert "really had" in row["lines_basis"], "the run reports the real figure afterwards"


def test_it_is_far_below_the_price_of_a_whole_page_review_at_the_same_rate():
    [whole] = estimate([CORRECT], 10)["runs"]
    [lines] = estimate([A], 10)["runs"]
    assert whole["certainty_bar"] is None and whole["lines_at_most"] is None and whole["lines_basis"] is None
    assert whole["calls_per_page"] == 3, "the whole-page review is priced as before"
    assert lines["cost_usd"] != whole["cost_usd"]


def test_variant_a_on_this_mac_costs_nothing_and_an_unpriced_place_is_unpriced():
    [here] = estimate([{**A, "runs_on": "this-mac", "provider_override": "omlx"}], 10)["runs"]
    assert here["cost_usd"] == 0.0 and here["lines_at_most"] == 330
    [other] = estimate([{**A, "runs_on": "cluster:acenet"}], 10)["runs"]
    assert other["cost_usd"] is None
