"""`designer.budget.basis-per-step` (#6295): each run of the estimate carries its basis as a field (`measured` · `assumed` · `free` ·
`unpriced`), per page, with words; never worked out in the app."""
from __future__ import annotations

from fichero_server.api.main import app
from fichero_server.recipes.start import estimate


def _run(runs_on, provider=None, model=None, job="read-a-page"):
    return {"card": "workflow", "runs_on": runs_on, "model_override": model, "provider_override": provider, "workflow_id": None,
            "job": job, "steps": [job], "workflow": job}


def test_a_cloud_run_is_assumed_with_its_price_a_page_and_the_words_say_so():
    (row,) = estimate([_run("cloud:anthropic", "anthropic", "claude-haiku-4-5")], 16)["runs"]
    assert row["basis_kind"] == "assumed" and row["cost_per_page_usd"] == row["cost_usd"] / 16
    assert row["basis_words"].startswith("16 pages × $") and "assumed" in row["basis_words"]


def test_a_local_run_is_free_and_says_free_on_this_mac():
    (row,) = estimate([_run("this-mac", job="find-lines")], 16)["runs"]
    assert (row["basis_kind"], row["basis_words"], row["cost_per_page_usd"]) == ("free", "free on this Mac", None)


def test_an_unpriced_model_is_unpriced_never_a_zero():
    (row,) = estimate([_run("cloud:nobody", "nobody", "no-such-model")], 16)["runs"]
    assert row["basis_kind"] == "unpriced" and row["cost_usd"] is None and row["cost_per_page_usd"] is None


def test_the_fields_are_in_the_contract():
    fields = app.openapi()["components"]["schemas"]["StartEstimateRun"]["properties"]
    assert {"basis_kind", "basis_words", "cost_per_page_usd", "measured_pages"} <= set(fields)
