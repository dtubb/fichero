"""`source.recipe.download-failure-waits` (#5352): a step waiting on a download that failed carries Retry (the download's
job) and the next candidate of its chain, so the run summary can act, not only say."""
from __future__ import annotations

from fichero_server.recipes.run_view import download_failures

LOCAL = {"id": "mlx-qwen", "model": {"provider": "mlx", "name": "qwen"}, "runs_on": "this-mac"}
CLOUD = {"id": "claude-vision", "model": {"provider": "anthropic", "name": "claude"}, "runs_on": "cloud:anthropic"}
CHOSEN = {"id": "es-hand", "model": {"provider": "kraken", "name": "es-hand"}, "runs_on": "this-mac"}
AWAITED = [{"steps": ["r"], "job_id": "dl1", "name": "es-hand"}]
RECIPE = {"steps": [{"id": "r", "job": "read-a-line", "model": {"provider": "kraken", "name": "es-hand"},
                     "chain": [CHOSEN, CLOUD, LOCAL]}]}


def got(states, *, awaited=AWAITED, recipe=RECIPE, cloud_allowed=False):
    return download_failures(awaited, states, recipe, cloud_allowed=cloud_allowed)


def test_a_failed_download_offers_retry_and_the_next_local_candidate():
    [row] = got({"dl1": {"state": "failed", "reason": "connection lost"}})
    assert row["steps"] == ["r"] and row["retry_job_id"] == "dl1" and row["reason"] == "connection lost"
    assert row["next_candidate"]["id"] == "mlx-qwen" and row["next_candidate"]["needs_permission"] is False


def test_only_a_cloud_candidate_left_needs_permission():
    recipe = {"steps": [{"id": "r", "chain": [CHOSEN, CLOUD]}]}
    [row] = got({"dl1": {"state": "cancelled", "reason": None}}, recipe=recipe)
    assert row["next_candidate"]["id"] == "claude-vision" and row["next_candidate"]["needs_permission"] is True
    [row] = got({"dl1": {"state": "failed", "reason": "x"}}, recipe=recipe, cloud_allowed=True)
    assert row["next_candidate"]["needs_permission"] is False


def test_a_download_that_landed_or_still_runs_offers_nothing():
    assert got({"dl1": {"state": "done", "reason": None}}) == []
    assert got({"dl1": {"state": "running", "reason": None}}) == []
    assert got({}) == []


def test_no_other_candidate_still_offers_retry():
    recipe = {"steps": [{"id": "r", "chain": [CHOSEN]}]}
    [row] = got({"dl1": {"state": "failed", "reason": "x"}}, recipe=recipe)
    assert row["retry_job_id"] == "dl1" and row["next_candidate"] is None
