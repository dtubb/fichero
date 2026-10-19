"""`source.onboard.setup-says-what-is-happening` (#5791, engine half): the Start plan sends the sentences the app shows."""
from __future__ import annotations

from fichero_server.recipes.start import download_sentence, plan_start


def _recipe(*steps):
    return {"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t", "steps": list(steps)}


def test_work_out_dates_says_how_it_works():
    plan = plan_start(_recipe({"id": "dates", "job": "work-out-dates"}), stays_local=True)
    runs = [r for r in plan["runs"] if r["job"] == "work-out-dates"]
    assert runs, plan
    how = runs[0]["how"]
    assert "not a model" in how and "feast days" in how and "regnal" in how and "this Mac" in how


def test_a_run_that_has_no_description_has_none():
    plan = plan_start(_recipe(
        {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}), stays_local=True)
    assert all(r.get("how") is None for r in plan["runs"])


def test_a_download_under_way_says_downloading_and_that_its_steps_wait():
    said = download_sentence({"name": "Qwen2.5-VL 7B", "model": "q", "size_mb": 5700, "steps": ["read"],
                              "downloading": True, "progress": "1.2 GB of 5.6 GB"})
    assert said.startswith("Downloading Qwen2.5-VL 7B") and "1.2 GB of 5.6 GB" in said and "wait" in said
    assert "not on this Mac" not in said


def test_a_download_not_begun_says_start_fetches_it_with_its_size():
    said = download_sentence({"model": "pp", "size_mb": 60, "steps": ["read"], "downloading": False})
    assert said == "pp is not on this Mac yet (60 MB): Start downloads it, and its steps wait for it."
    assert "size not stated" in download_sentence({"model": "pp", "steps": ["r"], "downloading": False})
