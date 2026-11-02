"""A step's prompt fragments ride to the read node with their versions (`image.enhance.reader-prompt-fragment`, #6199)."""
from __future__ import annotations


def test_start_carries_the_steps_fragments_with_their_versions_to_the_read_node():
    from fichero_server.recipes.start import plan_start
    from tests.unit.recipes.test_start_plan import _recipe

    step = {"id": "read", "job": "read-a-line", "runs_on": "this-mac", "model": {"cloud": "openai", "model": "gpt-5"},
            "prompt_fragments": ["ignore-show-through@1", "read-over-stamps@1"]}
    run = next(r for r in plan_start(_recipe(step), stays_local=False)["runs"] if r["job"] == "read-a-line")
    assert run["tool_config"]["transcribe"]["prompt_fragments"] == ["ignore-show-through@1", "read-over-stamps@1"]
    assert run["prompt_fragments"] == [{"id": "ignore-show-through", "version": 1}, {"id": "read-over-stamps", "version": 1}]
