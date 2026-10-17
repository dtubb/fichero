"""Start's estimate states each step's place and its cost basis; a place that is neither this Mac nor a priced
cloud call is unpriced, never $0 (#5590, `ai.where.estimate-names-the-place`)."""
from __future__ import annotations

from fichero_server.recipes.start import estimate


def _workflow(runs_on, model="", provider=""):
    return {"workflow": "w", "steps": ["s"], "runs_on": runs_on, "model_override": model,
            "provider_override": provider}


def test_this_mac_is_free_and_says_so():
    row = estimate([_workflow("this-mac")], 100)["runs"][0]
    assert row["where"] == "this-mac" and row["cost_usd"] == 0.0 and row["basis"] == "free on this Mac"


def test_a_cluster_or_other_place_is_unpriced_never_zero_and_makes_the_total_unknown():
    out = estimate([_workflow("cluster:hpc-1"), _workflow("this-mac")], 100)
    row = out["runs"][0]
    assert row["where"] == "cluster:hpc-1" and row["cost_usd"] is None and row["basis"] == "unpriced"
    assert out["total_cost_usd"] is None


def test_a_cloud_step_with_an_unknown_model_is_unpriced():
    row = estimate([_workflow("cloud:openai", model="no-such-model-xyz", provider="openai")], 100)["runs"][0]
    assert row["cost_usd"] is None and row["basis"] == "unpriced"


def test_the_routes_response_model_keeps_each_runs_basis():
    """The Start plan route answers through `StartEstimateRun`; a field it lacks is dropped from the response."""
    from fichero_server.api.routes.system.recipes import StartEstimateRun

    row = estimate([_workflow("cluster:hpc-1")], 100)["runs"][0]
    assert StartEstimateRun.model_validate(row).model_dump()["basis"] == "unpriced"
