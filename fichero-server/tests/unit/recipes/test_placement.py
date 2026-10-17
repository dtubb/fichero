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
