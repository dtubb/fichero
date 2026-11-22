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


def test_a_knob_is_read_from_the_database_once_not_per_call(app_db, monkeypatch):
    from fichero_server.db.app import get_app_db

    mrs.save_run_settings("kraken", {"threads": 3})
    db = get_app_db()
    reads = []
    real = db.get_setting
    monkeypatch.setattr(db, "get_setting", lambda key: reads.append(key) or real(key))
    for _ in range(5):
        assert kraken_runtime.reading_threads(8, 2) == 3
    assert len(reads) <= 1
    mrs.save_run_settings("kraken", {"threads": 5})
    assert kraken_runtime.reading_threads(8, 2) == 5, "a save drops the kept copy"


def test_setting_an_unknown_runtime_through_the_action_is_a_value_error(app_db):
    from fichero_server.actions.registry import registry
    from fichero_server.api.routes.system import activity  # noqa: F401  (registers the action)

    reg = registry.get("models.set_run_settings")
    with pytest.raises(ValueError):
        reg.execute(None, reg.params_model(runtime="nonesuch", values={}), None)


def test_the_mac_wide_model_writes_are_the_owners(app_db, monkeypatch):
    """Run settings and Unload Idle Models change the whole Mac: a signed-in non-owner is refused on the route and the
    action twin is declared app-owner-only; a read needs a signed-in person (#6325 H9)."""
    from types import SimpleNamespace

    from fastapi import HTTPException
    from fichero_server.actions.registry import registry
    from fichero_server.api.routes.auth import accounts
    from fichero_server.api.routes.system import activity

    for name in ("models.set_run_settings", "activity.unload_idle_models"):
        reg = registry.get(name)
        assert reg.owner_only and reg.owner_scope == "app", name
    by_path = {(r.path, m): r for r in activity.router.routes for m in r.methods}
    assert {d.call for d in by_path[("/activity/models/run-settings/{runtime}", "PUT")].dependant.dependencies} >= {
        accounts._require_owner_or_bootstrap}
    assert {d.call for d in by_path[("/activity/models/unload-idle", "POST")].dependant.dependencies} >= {
        accounts._require_owner_or_bootstrap}
    assert {d.call for d in by_path[("/activity/models/run-settings/{runtime}", "GET")].dependant.dependencies} >= {
        accounts._require_authenticated_or_bootstrap}

    monkeypatch.setattr(accounts, "_use_multiuser_auth", lambda: True)
    request = SimpleNamespace(state=SimpleNamespace(bootstrap_auth=False))
    monkeypatch.setattr(accounts, "_current_session_user", lambda request: None)
    with pytest.raises(HTTPException) as signed_out:
        accounts._require_authenticated_or_bootstrap(request)
    assert signed_out.value.status_code == 401
    monkeypatch.setattr(accounts, "_current_session_user", lambda request: SimpleNamespace(is_owner=False))
    accounts._require_authenticated_or_bootstrap(request)
    with pytest.raises(HTTPException) as editor:
        accounts._require_owner_or_bootstrap(request)
    assert editor.value.status_code == 403


def test_each_knob_names_the_engines_own_default_and_its_reason(app_db, monkeypatch):
    """`models.run-settings.per-model` (#6588): the value Auto means and why, per knob; a saved knob does not change it."""
    monkeypatch.delenv("FICHERO_COMPUTE_DEVICE", raising=False)
    monkeypatch.setattr(kraken_runtime, "pages_at_once_and_why", lambda person: (1, "the free memory holds one page"))
    monkeypatch.setattr("fichero_server.core.cores.cores_available", lambda: (8, "performance"))
    mrs.save_run_settings("kraken", {"threads": 3})
    got = mrs.defaults("kraken")
    assert set(got) == set(mrs.KNOBS["kraken"])
    assert got["pages_at_once"] == {"value": 1, "reason": "the free memory holds one page"}
    assert got["threads"]["value"] == 8 and "cores" in got["threads"]["reason"]
    assert got["batch_size"]["value"] == 1 and got["batch_size"]["reason"]
    assert got["device"] == {"value": "auto", "reason": got["device"]["reason"]} and got["device"]["reason"]


def test_the_line_finders_height_per_script_is_listed_read_only(app_db):
    heights = mrs.script_heights()
    assert heights["default"] == {"height": 1800, "base": "bundled"}
    assert heights["scripts"]["Hebr"] == {"height": 1200, "base": "2026"}
    assert heights["scripts"]["Newa"]["height"] == 300


def test_the_route_answers_the_defaults_and_the_heights(client, app_db):
    got = client.get("/api/activity/models/run-settings/kraken").json()
    assert set(got["defaults"]) == set(mrs.KNOBS["kraken"])
    assert got["defaults"]["batch_size"]["value"] == 1
    assert got["script_heights"]["scripts"]["Arab"]["height"] == 1200
