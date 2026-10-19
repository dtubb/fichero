"""`source.recipe.runs-on-binds-to-a-target` and `source.recipe.placement-by-scale` (#4950, #5589): the project binds
its cluster (`answers.cluster`, a cluster set up here, by the name Set Up shows); a read the plan places there by scale
is sent to that cluster as a read-at-scale run under its step, never read on this Mac while the plan says cluster.

WHY: the plan placed every step on this Mac ("No cluster is set up") because nothing bound a cluster to a step.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.recipes.start import place_runs
from tests.unit.api.test_add_a_layer_later import (  # noqa: F401  (fixtures)
    _kraken_readers_on_this_mac,
    hold_the_run,
    project,
)

KRAKEN_RUN = {"steps": ["read"], "job": "read-a-line", "card": "workflow", "provider_override": "kraken",
              "model_override": "catmus-medieval"}
VISION_RUN = {**KRAKEN_RUN, "provider_override": "omlx", "model_override": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"}


def test_a_kraken_read_of_a_hundred_thousand_pages_places_on_the_bound_cluster():
    [run] = place_runs([dict(KRAKEN_RUN)], 100_000, cloud_allowed=True, bound_cluster="rorqual")
    assert run["place"] == "cluster" and run["target"] == "rorqual"


def test_a_vision_read_stays_here_and_says_why_a_cluster_is_not_used():
    [run] = place_runs([dict(VISION_RUN)], 100_000, cloud_allowed=True, bound_cluster="rorqual")
    assert run["place"] == "this-mac" and run["target"] is None
    assert "vision reader" in run["why"] and "rorqual" in run["why"]


def test_a_cluster_that_is_not_a_string_is_refused_in_words():
    from fichero_server.recipes.answers import normalise

    with pytest.raises(ValueError, match="cluster"):
        normalise({"purposes": ["transcribe"], "cluster": 3}, strict=True)


def _clusters(monkeypatch, owner=True):
    from fichero_server.api.routes.ai import hpc
    from fichero_server.api.routes.auth import accounts
    from fichero_server.db import app as app_db

    def check(request):
        if not owner:
            raise HTTPException(status_code=403, detail="owner access required")

    monkeypatch.setattr(accounts, "_require_owner_or_bootstrap", check)
    monkeypatch.setattr(app_db, "get_app_db", lambda: None)
    monkeypatch.setattr(hpc, "_load_clusters", lambda db: {"rq-1": {"name": "Rorqual", "cluster_id": "rq-1"}})


@pytest.mark.parametrize("owner", [True, False])
def test_the_plan_binds_the_projects_cluster_for_the_owner_only(client, project, monkeypatch, owner):  # noqa: F811
    from fichero_server.recipes import start

    _clusters(monkeypatch, owner)
    seen = []

    monkeypatch.setattr(start, "place_runs", lambda runs, pages, **kw: seen.append(kw["bound_cluster"]) or runs)
    setup = client.get("/api/recipes/project").json()
    r = client.put("/api/recipes/project", json={"answers": {**setup["answers"], "cluster": "Rorqual"},
                                                  "recipe": setup["recipe"]})
    assert r.status_code == 200, r.text
    client.get("/api/recipes/project/start")
    assert seen[-1] == ("rq-1" if owner else None)


def test_a_cluster_not_set_up_here_binds_nothing(client, project, monkeypatch):  # noqa: F811
    from fichero_server.recipes import start

    _clusters(monkeypatch)
    seen = []
    monkeypatch.setattr(start, "place_runs", lambda runs, pages, **kw: seen.append(kw["bound_cluster"]) or runs)
    setup = client.get("/api/recipes/project").json()
    client.put("/api/recipes/project", json={"answers": {**setup["answers"], "cluster": "Narval"},
                                             "recipe": setup["recipe"]})
    client.get("/api/recipes/project/start")
    assert seen[-1] is None


def _pages_may_leave(monkeypatch, allowed):
    from fichero_server.recipes import project

    monkeypatch.setattr(project, "read_project_setup", lambda library: {"answers": {"cloud_allowed": allowed},
                                                                        "recipe": None})


def test_a_read_placed_on_the_cluster_is_sent_there_under_its_step(db, monkeypatch):
    from fichero_server.recipes import runner
    from fichero_server.remote_read import job as read_job

    _pages_may_leave(monkeypatch, True)

    sent, waited = [], []
    monkeypatch.setattr(read_job, "start", lambda db, request, *, started_by: sent.append((request, started_by))
                        or {"job_id": "read-1"})
    monkeypatch.setattr(runner, "_wait", lambda db, child, parent: waited.append((child, parent)) or (child, "done", None))
    card = {**KRAKEN_RUN, "place": "cluster", "target": "rq-1"}

    assert runner._run_card(db, card, ["p1", "p2"], {}, "recipe-job", {}, "daniel") == ("read-1", "done", None)
    [(request, who)] = sent
    assert (request.target, request.reader, request.card, request.scope_ids) == ("rq-1", "kraken", "catmus-medieval",
                                                                               ["p1", "p2"])
    assert request.pages_may_leave and request.parent_job_id == "recipe-job" and who == "daniel"
    assert waited == [("read-1", "recipe-job")]


def test_a_cluster_that_refuses_fails_the_step_by_name(db, monkeypatch):
    from fichero_server.recipes import runner
    from fichero_server.remote_read import job as read_job
    from fichero_server.remote_read.slurm_target import NoKey

    def refuse(db, request, *, started_by):
        raise NoKey("cluster rq-1: the app's key and sign-in step are not built yet (#5238)")

    monkeypatch.setattr(read_job, "start", refuse)
    _pages_may_leave(monkeypatch, True)
    child, state, why = runner._run_card(db, {**KRAKEN_RUN, "place": "cluster", "target": "rq-1"}, ["p1"], {},
                                         "recipe-job", {}, "daniel")
    assert (child, state) == (None, "failed") and why and "rq-1" in why and "#5238" in why


def test_pages_may_not_leave_said_after_start_refuses_the_cluster_step_by_name(db, monkeypatch):
    """The plan placed the read on the cluster while pages could leave; the person then said no. The yes is read
    when the read is sent, so nothing is sent and the step says why (review 153)."""
    from fichero_server.recipes import runner
    from fichero_server.remote_read import job as read_job

    sent = []
    monkeypatch.setattr(read_job, "start", lambda db, request, *, started_by: sent.append(request) or {"job_id": "x"})
    _pages_may_leave(monkeypatch, False)
    child, state, why = runner._run_card(db, {**KRAKEN_RUN, "place": "cluster", "target": "rq-1"}, ["p1"], {},
                                         "recipe-job", {}, "daniel")
    assert (child, state, sent) == (None, "failed", [])
    assert why == "pages may not leave this Mac; this step was placed on rq-1"
