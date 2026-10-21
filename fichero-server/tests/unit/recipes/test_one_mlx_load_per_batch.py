"""One MLX load per batch, kept through spaCy (`source.recipe.step-major-per-batch`, owner ruling 2026-10-21): per batch
Kraken, MLX correct, spaCy (MLX kept), the MLX text steps, embedding. spaCy is light: it never releases the served model,
and the idle stop does not take the model while a batch still has steps to run."""
from __future__ import annotations

from fichero_server.api.routes.ai import local_inference
from fichero_server.execution import jobs
from tests.unit.jobs.test_one_model_at_a_time_on_the_lane import (  # noqa: F401 -- fixtures
    KRAKEN, VLM, _wait_for, lane)
from tests.unit.recipes.test_recipe_batches_to_spec import (  # noqa: F401 -- fixtures
    _finished, _save, _start, archive, engine, steps)


def test_a_spacy_job_between_two_mlx_jobs_releases_nothing(db, lane, monkeypatch):
    from fichero_server.execution.jobs import Kind

    monkeypatch.setitem(jobs.KINDS, "spacy-omt", Kind(run=lambda db, subject: lane.ran.append(subject), model="spacy",
                                                       lane="local-ml", name="Names"))
    jobs.enqueue(db, VLM, "correct")
    assert _wait_for(lambda: "correct" in lane.ran)
    jobs.enqueue(db, "spacy-omt", "names")
    assert _wait_for(lambda: "names" in lane.ran)
    jobs.enqueue(db, VLM, "statements")
    assert _wait_for(lambda: "statements" in lane.ran)

    assert lane.swaps == [], lane.swaps  # the served model was loaded once: nothing released it
    assert jobs._scheduler.lanes["local-ml"].loaded_model == "omlx:big-vlm"


def test_the_idle_stop_waits_while_a_run_holds_the_model(monkeypatch):
    stopped, rearmed = [], []

    class Manager:
        profile = type("P", (), {"id": "m", "managed_by_app": True})()
        process = type("Proc", (), {"is_running": staticmethod(lambda: True)})()

        async def stop(self):
            stopped.append(1)

    manager = Manager()
    monkeypatch.setitem(local_inference._MANAGERS, "m", manager)
    monkeypatch.setattr(local_inference, "_stop_when_idle", lambda m: rearmed.append(m))
    local_inference.hold_served_models("run-1")
    try:
        local_inference._stop_if_still_idle(manager)
        assert stopped == [] and rearmed == [manager]
    finally:
        local_inference.let_go_served_models("run-1")
    local_inference._stop_if_still_idle(manager)
    assert stopped == [1]


def test_a_run_holds_the_served_model_for_every_card_of_every_batch_and_lets_go_after(client, db, archive, steps, monkeypatch):
    """The hold covers each card of each batch (lines, names, ...) and is gone when the run ends."""
    from fichero_server.recipes import runner

    monkeypatch.setattr(runner, "BATCH_PAGE_LIMIT", 1)
    held = []
    run_card = steps.run

    def seen(db, card, documents, parent):
        held.append(local_inference.served_models_held())
        return run_card(db, card, documents, parent)

    monkeypatch.setattr(runner, "_run_workflow", seen)
    _save(client)
    run = _finished(client, _start(client, folder_id=archive["B"])["started"]["job_id"])

    assert run["state"] == "done" and held == [True] * 4, held
    assert not local_inference.served_models_held()
