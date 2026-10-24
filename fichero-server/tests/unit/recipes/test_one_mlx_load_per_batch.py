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
        profile = type("P", (), {"id": "m", "managed_by_app": True, "model_id": "mlx-a"})()
        process = type("Proc", (), {"is_running": staticmethod(lambda: True)})()

        async def stop(self):
            stopped.append(1)

    manager = Manager()
    manager.profile.model_id = "mlx-a"
    monkeypatch.setitem(local_inference._MANAGERS, "m", manager)
    monkeypatch.setattr(local_inference, "_stop_when_idle", lambda m: rearmed.append(m))
    local_inference.hold_served_models("run-1", {"mlx-a"})
    try:
        local_inference._stop_if_still_idle(manager)
        assert stopped == [] and rearmed == [manager]
    finally:
        local_inference.let_go_served_models("run-1")
    local_inference._stop_if_still_idle(manager)
    assert stopped == [1]


def test_a_hold_is_for_the_models_it_names(monkeypatch):
    """## 849 LOW: a run holding model A does not keep a server serving model B loaded."""
    local_inference.hold_served_models("run-1", {"mlx-a"})
    try:
        assert local_inference.served_models_held("mlx-a") and not local_inference.served_models_held("mlx-b")
    finally:
        local_inference.let_go_served_models("run-1")
    assert not local_inference.served_models_held()


def _run_with_served_step_at(index, client, archive, steps, monkeypatch):
    from fichero_server.recipes import runner

    monkeypatch.setattr(runner, "BATCH_PAGE_LIMIT", 1)
    monkeypatch.setattr(runner, "_served_steps", lambda cards: [(index, "mlx-a")])
    held = []
    run_card = steps.run

    def seen(db, card, documents, parent, adopt=None):
        held.append(local_inference.served_models_held("mlx-a"))
        return run_card(db, card, documents, parent)

    monkeypatch.setattr(runner, "_run_workflow", seen)
    _save(client)
    run = _finished(client, _start(client, folder_id=archive["B"])["started"]["job_id"])
    assert run["state"] == "done", run
    assert not local_inference.served_models_held()  # gone when the run ends
    return held


def test_a_run_holds_the_served_model_through_the_last_step_that_uses_it(client, db, archive, steps, monkeypatch):
    """The served model is used by the second card (names, standing in for the last MLX text step): held for both cards of both batches."""
    assert _run_with_served_step_at(1, client, archive, steps, monkeypatch) == [True] * 4


def test_the_hold_ends_after_the_last_served_step_not_at_the_batch_end(client, db, archive, steps, monkeypatch):
    """## 849 LOW: when only the first card uses the served model, the second card (and what follows) runs without the hold."""
    assert _run_with_served_step_at(0, client, archive, steps, monkeypatch) == [True, False, True, False]


def test_the_hold_names_the_id_the_server_serves_however_the_card_says_it(monkeypatch):
    """## 856 MED: the idle stop compares the store id; a card that says `omlx/<id>`, a default alias or nothing is held under it."""
    from fichero_server.llm import local_model_choice
    from fichero_server.recipes import runner

    monkeypatch.setattr(local_model_choice, "model_to_serve",
                        lambda name, **k: {"omlx/Org/Big-4bit": "Org/Big-4bit-mlx", "default": "Org/Default-mlx",
                                           None: "Org/Default-mlx"}.get(name, name))
    cards = [{"provider_override": "omlx", "model_override": "omlx/Org/Big-4bit"},
             {"provider_override": "omlx", "model_override": None},
             {"provider_override": "openai", "model_override": "gpt-5"}]
    served = runner._served_steps(cards)
    assert served == [(0, "Org/Big-4bit-mlx"), (1, "Org/Default-mlx")]
    local_inference.hold_served_models("run-1", {m for _, m in served})
    try:
        assert local_inference.served_models_held("Org/Big-4bit-mlx") and local_inference.served_models_held("Org/Default-mlx")
        assert not local_inference.served_models_held("omlx/Org/Big-4bit")  # the raw name is never what the server reports
    finally:
        local_inference.let_go_served_models("run-1")
