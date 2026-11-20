"""`models.settings.run-knobs` (#6588): the knobs the window edits are the ones Kraken's runtime reads."""
from __future__ import annotations

import pytest
from fichero_server.llm import kraken_runtime, model_run_settings as mrs


def test_unset_knobs_are_none_and_a_saved_one_is_read_back(app_db):
    assert mrs.run_settings("kraken") == {"pages_at_once": None, "threads": None, "batch_size": None, "device": None}
    mrs.save_run_settings("kraken", {"threads": 3})
    mrs.save_run_settings("kraken", {"batch_size": 4})
    assert mrs.run_settings("kraken")["threads"] == 3 and mrs.run_settings("kraken")["batch_size"] == 4
    mrs.save_run_settings("kraken", {"threads": None})
    assert mrs.run_settings("kraken")["threads"] is None


@pytest.mark.parametrize("values", [{"threads": 0}, {"pages_at_once": 99}, {"device": "tpu"}, {"precision": "16"},
                                    {"batch_size": True}, {"threads": "2"}])
def test_a_value_out_of_range_or_unknown_is_refused_not_clamped(app_db, values):
    with pytest.raises(ValueError):
        mrs.save_run_settings("kraken", values)
    assert mrs.run_settings("kraken")["threads"] is None


def test_kraken_reads_the_settings(app_db, monkeypatch):
    assert kraken_runtime.reader_batch_size() == 1
    assert kraken_runtime.reading_threads(8, 2) == 4, "the engine's rule: the cores shared by the pages"
    mrs.save_run_settings("kraken", {"batch_size": 8, "threads": 3, "pages_at_once": 4})
    assert kraken_runtime.reader_batch_size() == 8
    assert kraken_runtime.reading_threads(8, 2) == 3
    seen = []
    monkeypatch.setattr(kraken_runtime, "page_fan_out", lambda cap: seen.append(cap) or cap)
    monkeypatch.setattr("fichero_server.core.compute_preferences.priority_for", lambda person: "fast")
    monkeypatch.setattr("fichero_server.core.cores.is_a_mac_pipeline_host", lambda source: True)
    monkeypatch.setattr("fichero_server.execution.jobs.resuming_gently", lambda: False)
    monkeypatch.setattr("fichero_server.execution.throttle.memory_is_busy", lambda: False)
    assert kraken_runtime.pages_at_once(True) == 4 and seen == [4], "the setting is the cap; memory still bounds it"


def test_the_device_setting_beats_the_global_one(app_db, monkeypatch):
    monkeypatch.delenv("FICHERO_COMPUTE_DEVICE", raising=False)
    assert kraken_runtime.reading_device() == "auto"
    mrs.save_run_settings("kraken", {"device": "cpu"})
    assert kraken_runtime.reading_device() == "cpu"
    monkeypatch.setenv("FICHERO_COMPUTE_DEVICE", "gpu")
    assert kraken_runtime.reading_device() == "gpu", "the environment's override still wins"


def test_the_cost_is_memory_from_the_engines_figure_and_time_unmeasured(app_db):
    one = mrs.cost("kraken", {"pages_at_once": 1})
    three = mrs.cost("kraken", {"pages_at_once": 3})
    assert three["memory_bytes"] - one["memory_bytes"] == 2 * kraken_runtime._PAGE_BYTES
    assert one["seconds_per_page"] is None


def test_the_route_reads_and_saves_a_runtimes_settings_with_their_cost(client, app_db):
    got = client.get("/api/activity/models/run-settings/kraken")
    assert got.status_code == 200, got.text
    assert got.json()["settings"]["threads"] is None and got.json()["cost"]["seconds_per_page"] is None

    one = client.put("/api/activity/models/run-settings/kraken", json={"pages_at_once": 1})
    saved = client.put("/api/activity/models/run-settings/kraken", json={"threads": 2, "pages_at_once": 3})
    assert saved.status_code == 200, saved.text
    assert saved.json()["settings"]["threads"] == 2
    assert saved.json()["cost"]["memory_bytes"] - one.json()["cost"]["memory_bytes"] == 2 * kraken_runtime._PAGE_BYTES
    assert client.put("/api/activity/models/run-settings/kraken", json={"threads": 0}).status_code == 422
    assert client.get("/api/activity/models/run-settings/nonesuch").status_code == 404
