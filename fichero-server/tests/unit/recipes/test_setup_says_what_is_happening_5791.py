"""`source.onboard.setup-says-what-is-happening` (#5791, engine half): the Start plan sends the sentences the app shows."""
from __future__ import annotations

from fichero_server.recipes.start import download_sentence, plan_start
from tests.unit.recipes.test_hub_discovery_quality_5594 import store  # noqa: F401  (fixture)


def _recipe(*steps):
    return {"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t", "steps": list(steps)}


def test_work_out_dates_says_how_it_works():
    plan = plan_start(_recipe({"id": "dates", "job": "work-out-dates"}), stays_local=True)
    runs = [r for r in plan["runs"] if r["job"] == "work-out-dates"]
    assert runs, plan
    from fichero_server.recipes.topics import get_topic

    written = get_topic("work-out-dates").long
    assert written.startswith("How it works:"), "the sentence lives in topics.yaml, once"
    rest = written[len("How it works:"):].strip()
    assert runs[0]["how"] == rest[:1].upper() + rest[1:]
    assert "not a model" in runs[0]["how"] and "regnal" in runs[0]["how"]


def test_a_job_whose_topic_has_no_how_it_works_gives_none():
    from fichero_server.recipes.start import how_it_works

    assert how_it_works("find-lines") is None and how_it_works("no-such-job") is None


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


def test_a_candidate_whose_download_is_under_way_carries_its_activity_job(client, db, store, monkeypatch, tmp_path):  # noqa: F811
    """#5791 item 3: the Find a Reader sheet shows a download under way from the candidate's own fields, not by
    searching Activity for a job id."""
    from fichero_server.llm.local_models import enqueue_download

    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken"))
    params = {"scripts": "Latn", "languages": "es", "material": "handwriting", "mac_memory_gb": 32}
    pin = "kraken:zenodo/10.5281/zenodo.12743230@unpinned"
    before = {c["id"]: c for c in client.get("/api/recipes/candidates", params=params).json()["items"]}[pin]
    assert before["download"]["downloading"] is False and before["download"]["job_id"] is None

    job_id = enqueue_download(db, "kraken", "kraken-catmus-medieval")
    after = {c["id"]: c for c in client.get("/api/recipes/candidates", params=params).json()["items"]}[pin]
    assert after["download"]["downloading"] is True and after["download"]["job_id"] == job_id
    assert after["availability_words"].startswith("Downloading")
