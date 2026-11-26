"""`activity.run.stage-by-stage-no-model-juggling` (#5939): a run's pages queued page by page across two heavy models are taken
stage by stage by the model lane: every Kraken page, then every MLX page, so each model loads once, never once per page."""
from __future__ import annotations

from fichero_server.execution import jobs
from tests.unit.jobs.test_job_queue import _kind, _wait_for  # noqa: F401  (the real-lane helpers)

PAGES = 6


def _switches(models: list[str]) -> int:
    """How many times the lane's loaded model changes over the order the pages ran in (each change is a load)."""
    return sum(1 for before, after in zip(models, models[1:]) if before != after)


def test_pages_queued_page_by_page_run_stage_by_stage(db, monkeypatch):
    ran: list[str] = []
    _kind(monkeypatch, "t-kraken", "kraken:blla", ran)
    _kind(monkeypatch, "t-mlx", "omlx:qwen", ran)
    jobs.set_paused(True)
    for page in range(PAGES):  # the juggling order: a Kraken page, an MLX page, the next page ...
        jobs.enqueue(db, "t-kraken", f"kraken-{page}")
        jobs.enqueue(db, "t-mlx", f"mlx-{page}")
    jobs.set_paused(False)
    assert _wait_for(lambda: len(ran) == 2 * PAGES)
    models = [name.split("-")[0] for name in ran]
    assert _switches(models) == 1, ran  # one load of each heavy model: Kraken's block, then the MLX block
    assert models[0] == "kraken"
