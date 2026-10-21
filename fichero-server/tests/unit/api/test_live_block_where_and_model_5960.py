"""`activity.summary.where-and-model` (#5960): each live block names the model in words and where it runs (this Mac, an own
machine, a provider), from the running stage's job rows. Pure over the stage run's tree, so the shapes are written out."""
from __future__ import annotations

from fichero_server.api.main import app
from fichero_server.api.routes.system.activity_pages import where_and_model


def _row(state: str, model: str | None = None, places: dict | None = None, children: list | None = None) -> dict:
    return {"state": state, "model": model, "places": places or {}, "children": children or []}


def test_a_local_reader_is_named_and_runs_on_this_mac():
    stage = _row("running", places={"this_mac": 3}, children=[_row("running", "kraken:blla"), _row("done", "kraken:blla")])
    assert where_and_model(stage) == ("Kraken", "on this Mac")


def test_a_cloud_model_is_named_by_its_own_name_and_runs_in_the_cloud():
    stage = _row("running", places={"provider": 2}, children=[_row("running", "anthropic/claude-haiku-4.5")])
    assert where_and_model(stage) == ("claude-haiku-4.5", "in the cloud")


def test_an_own_machine_is_said_so():
    stage = _row("running", places={"own_machine": 1}, children=[_row("running", "mlx-community/Qwen2.5-VL-7B")])
    assert where_and_model(stage) == ("Qwen2.5-VL-7B", "on your own machine")


def test_the_place_most_calls_ran_in_wins_and_a_running_row_names_the_model():
    stage = _row("running", places={"this_mac": 1, "provider": 4}, children=[
        _row("done", "kraken:blla"), _row("running", "openai/gpt-4o")])
    assert where_and_model(stage) == ("gpt-4o", "in the cloud")


def test_nothing_known_says_nothing():
    assert where_and_model(_row("running")) == (None, None)


def test_the_live_block_carries_both():
    fields = app.openapi()["components"]["schemas"]["LiveBlock"]["properties"]
    assert {"model", "where"} <= set(fields)
