"""Where a step runs by the project's scale (`source.recipe.placement-by-scale`, #5589)."""
from __future__ import annotations

from fichero_server.recipes.placement import place_step


def test_a_thousand_pages_place_here_and_a_hundred_thousand_on_the_bound_cluster():
    assert place_step(1_000, pages_may_leave=True, bound_cluster="rorqual")["place"] == "this-mac"
    placed = place_step(100_000, pages_may_leave=True, bound_cluster="rorqual")
    assert placed["place"] == "cluster" and placed["target"] == "rorqual"


def test_pages_that_may_not_leave_stay_here_whatever_the_scale():
    placed = place_step(100_000, pages_may_leave=False, bound_cluster="rorqual")
    assert placed["place"] == "this-mac" and "may not leave" in placed["why"]


def test_a_recipe_with_no_bound_cluster_never_places_there_and_says_so():
    placed = place_step(100_000, pages_may_leave=True, bound_cluster=None)
    assert placed["place"] == "this-mac" and "No cluster is set up" in placed["why"]


def test_the_threshold_is_the_plans_to_set():
    assert place_step(500, pages_may_leave=True, bound_cluster="r", threshold=100)["place"] == "cluster"


def test_each_read_step_of_the_plan_says_where_it_runs_and_what_it_costs():
    from fichero_server.recipes.start import place_runs

    runs = [{"steps": ["read"], "job": "read-a-line", "card": "workflow"}, {"steps": ["embed"], "job": "embed", "card": "embed"}]
    [row] = place_runs(runs, 100_000, cloud_allowed=True)
    assert row["steps"] == ["read"] and row["place"] == "this-mac" and "No cluster is set up" in row["why"]
    assert row["sizing"] == "measured by a 1,000-page pilot"
    [row] = place_runs(runs, 100_000, cloud_allowed=True, bound_cluster="rorqual", pages_per_second=2.0)
    assert row["place"] == "cluster" and row["target"] == "rorqual"
    assert row["sizing"]["shard_size"] >= 1 and row["sizing"]["gpu_hours"] == 100_000 / 2.0 / 3600
