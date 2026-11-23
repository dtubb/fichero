"""The Models tree (`activity.window.models-tree`, `activity.resources.everything-measured`, #6588; the owner 2026-11-15:
"local/remote/cloud then provider then model … visualise if they're loaded or not, or active or not … how much RAM").

Acceptance: with Kraken reading and an embedder loaded idle, Kraken is active, the embedder loaded without being active,
with its resident size; a cloud model used this morning is listed, not loaded; a read on a cluster is remote."""
from __future__ import annotations

import json
from datetime import timedelta

from fichero_server.core.timeutil import utc_now
from fichero_server.execution import jobs
from fichero_server.workflows import activity_models


def _job(db, job_id, *, kind, model, state, detail=None, target=None, minutes_ago=5):
    started = (utc_now() - timedelta(minutes=minutes_ago)).replace(tzinfo=None)
    db.execute("INSERT INTO jobs (id, kind, subject, model, state, attempts, started_by, created_at, started_at, finished_at, "
               "detail, target) VALUES (?, ?, 's', ?, ?, 0, 'person', ?, ?, ?, ?, ?)",
               [job_id, kind, model, state, started, started,
                None if state == "running" else started + timedelta(seconds=30), detail, target])


def test_each_model_is_placed_loaded_active_and_measured(db, app_db):
    jobs._ensure(db)
    _job(db, "k1", kind="kraken-lines", model="kraken:blla", state="running")
    _job(db, "k0", kind="kraken-lines", model="kraken:blla", state="done", minutes_ago=10)
    call = {"provider": "anthropic", "model": "claude-sonnet", "place": "provider", "input_tokens": 10, "output_tokens": 5}
    _job(db, "c1", kind="describe", model="anthropic:claude-sonnet", state="done", detail=json.dumps({"usage": [call, call]}))
    _job(db, "r1", kind="read-at-scale", model="trocr", state="done", target="acenet")
    held = [{"name": "nomic-embed", "kind": "search embedder", "memory_bytes": 312_000_000}]

    found = {(m["place"], m["provider"], m["name"]): m for m in activity_models.models(db, held=held, installed=[])}

    kraken = found[("this-mac", "Kraken", "blla")]
    assert kraken["active"] and kraken["running"] == 1 and kraken["pages_today"] == 1
    embedder = found[("this-mac", "Embeddings", "nomic-embed")]
    assert embedder["loaded"] and not embedder["active"] and embedder["memory_bytes"] == 312_000_000
    cloud = found[("cloud", "Anthropic", "claude-sonnet")]
    assert cloud["calls_today"] == 2 and not cloud["loaded"] and cloud["memory_bytes"] is None
    assert ("remote", "acenet", "trocr") in found, "a read on a cluster of the person's is remote"


def test_the_tree_is_this_mac_then_remote_then_cloud():
    assert activity_models.PLACES == ("this-mac", "remote", "cloud")
    assert activity_models.place_and_provider("ollama:llama3") == ("this-mac", "Ollama", "llama3")
    assert activity_models.place_and_provider("openai:gpt-4o-mini") == ("cloud", "OpenAI", "gpt-4o-mini")
    assert activity_models.place_and_provider("apple-vision")[:2] == ("this-mac", "Apple")


def test_a_model_installed_and_not_held_is_listed_not_loaded(db):
    """WHY (owner 2026-11-16): the tree showed only what ran today, so a quiet project showed no models at all; every model
    installed on this Mac is listed, hollow until it is held, and one held is one row, loaded."""
    jobs._ensure(db)
    held = [{"name": "Kraken: blla", "kind": "Kraken", "memory_bytes": 1}]
    installed = [("Kraken", "blla"), ("Kraken", "catmus"), ("MLX", "Chandra-OCR")]

    found = {(m["place"], m["provider"], m["name"]): m
             for m in activity_models.models(db, held=held, installed=installed)}

    assert found[("this-mac", "Kraken", "blla")]["loaded"], "held and installed: one row, loaded"
    assert not found[("this-mac", "Kraken", "catmus")]["loaded"]
    assert not found[("this-mac", "MLX", "Chandra-OCR")]["loaded"]
    assert sum(1 for key in found if key[1] == "Kraken" and key[2] == "blla") == 1


def test_every_place_set_up_is_listed_used_or_not(app_db):
    """WHY (owner 2026-11-16): the places work can run (this Mac, another Mac, a cluster, the cloud) are in the tree
    before anything ran there: another Mac by its address, a cluster by its name, each cloud provider set up."""
    from fichero_server.models import Provider, ProviderType

    app_db.save_provider(Provider(id="p-remote", name="Studio", provider_type=ProviderType("ollama"),
                                  api_base="http://studio.example:11434"))
    app_db.save_provider(Provider(id="p-here", name="Here", provider_type=ProviderType("lmstudio"),
                                  api_base="http://127.0.0.1:1234"))
    app_db.save_provider(Provider(id="p-cloud", name="Claude", provider_type=ProviderType("anthropic")))
    app_db.set_setting("hpc.clusters", json.dumps({"acenet": {"cluster_id": "acenet", "name": "ACENET"}}))

    listed = [(p["place"], p["provider"]) for p in activity_models.places()]

    assert listed[0] == ("this-mac", "This Mac"), "this Mac first, always"
    assert ("remote", "studio.example") in listed, "another Mac by its address"
    assert ("remote", "ACENET") in listed, "a cluster by its name"
    assert ("cloud", "Anthropic") in listed
    assert not any(provider == "127.0.0.1" for _place, provider in listed), "a server on this Mac is not another Mac"
    order = [place for place, _provider in listed]
    assert order == sorted(order, key=activity_models.PLACES.index)


def test_the_route_answers_the_list(client, db, monkeypatch):
    monkeypatch.setattr(activity_models, "installed_on_this_mac", lambda: [])  # never what this Mac has installed
    jobs._ensure(db)
    _job(db, "k1", kind="kraken-lines", model="kraken:blla", state="running")
    answer = client.get("/api/activity/models")
    assert answer.status_code == 200, answer.text
    assert any(m["provider"] == "Kraken" for m in answer.json()["models"])
    assert answer.json()["places"][0] == {"place": "this-mac", "provider": "This Mac", "account": "ready", "egress": "this-mac"}


def test_this_mac_is_measured_or_says_it_is_not(client, db, monkeypatch):
    """`activity.resources.everything-measured`: this Mac's memory used of its total, its processor's load and each lane's
    jobs running of its width; what nothing measures is null, never 0."""
    jobs._ensure(db)
    registered = next(kind for kind, k in jobs.KINDS.items() if k.lane == "network") if any(
        k.lane == "network" for k in jobs.KINDS.values()) else None
    if registered:
        _job(db, "n1", kind=registered, model="anthropic:claude", state="running")

    mac = activity_models.this_mac(db, memory=(16 * 2**30, 25), load=4.0)

    assert mac["memory_total_bytes"] == 16 * 2**30 and mac["memory_used_bytes"] == 12 * 2**30
    assert mac["processor_percent"] is not None and mac["processor_percent"] > 0
    lanes = {lane["lane"]: lane for lane in mac["lanes"]}
    assert lanes["network"]["width"] == jobs.LANES["network"]
    if registered:
        assert lanes["network"]["busy"] == 1
    import os

    def no_load():
        raise OSError("not measured here")

    monkeypatch.setattr(os, "getloadavg", no_load)
    unmeasured = activity_models.this_mac(db, memory=(None, None))
    assert unmeasured["memory_used_bytes"] is None and unmeasured["processor_percent"] is None

    monkeypatch.setattr(activity_models, "installed_on_this_mac", lambda: [])  # never what this Mac has installed
    answer = client.get("/api/activity/models")
    assert answer.status_code == 200, answer.text
    assert answer.json()["this_mac"]["lanes"], "the lanes and their widths are always known"


def test_a_request_with_many_remote_calls_reads_the_provider_list_once(db, app_db, monkeypatch):
    """`call_key` is handed the provider hosts; a listing never reads the provider list per remote call (#6588)."""
    jobs._ensure(db)
    call = {"provider": "ollama", "model": "llama", "place": "own_machine", "input_tokens": 1, "output_tokens": 1}
    for i in range(5):
        _job(db, f"rc{i}", kind="describe", model="ollama:llama", state="done", detail=json.dumps({"usage": [call, call]}))
    reads = []
    original = app_db.list_providers
    monkeypatch.setattr(app_db, "list_providers", lambda: reads.append(1) or original())

    found = activity_models.models(db, held=[], installed=[])

    assert sum(m["calls_today"] for m in found if m["place"] == "remote") == 10
    assert len(reads) == 1


def test_a_loaded_kraken_and_yolo_model_are_listed_loaded_6745(db, monkeypatch):
    """#6745: with Kraken blla and the YOLO layout model in memory, the engine's held list names both, and the Models
    answer lists each as loaded on this Mac."""
    import sys

    from fichero_server.execution import models_held
    from fichero_server.llm import kraken_runtime, yolo_runtime

    jobs._ensure(db)
    monkeypatch.setitem(kraken_runtime._RESIDENT, "segment", ("blla", object()))
    monkeypatch.setitem(yolo_runtime._LOADED, "yolo-doclaynet-11n", object())
    monkeypatch.setitem(sys.modules, "fichero_server.llm.yolo_runtime", yolo_runtime)
    held = models_held.models_held()
    assert {"Kraken", "YOLO layout"} <= {h["kind"] for h in held}

    found = {(m["provider"], m["name"]): m for m in activity_models.models(db, held=held, installed=[])}
    assert found[("Kraken", "blla")]["loaded"] and found[("Kraken", "blla")]["place"] == "this-mac"
    assert found[("YOLO layout", "yolo-doclaynet-11n")]["loaded"]


def test_a_places_account_comes_from_a_probe_and_the_key_a_call_uses(app_db, monkeypatch):
    """`models.row.account-from-a-probe` (#5369, #4303, #5367): another Mac reads Not reachable when its probe refuses,
    a cloud provider reads Ready with an app-supplied key and Needs key without one; a cluster nothing probes is None."""
    from fichero_server.models import Provider, ProviderType
    from fichero_server.security import provider_keys

    app_db.save_provider(Provider(id="p-remote", name="Studio", provider_type=ProviderType("ollama"),
                                  api_base="http://studio.example:11434"))
    app_db.save_provider(Provider(id="p-cloud", name="Claude", provider_type=ProviderType("anthropic")))
    app_db.set_setting("hpc.clusters", json.dumps({"acenet": {"cluster_id": "acenet", "name": "ACENET"}}))
    monkeypatch.setattr("fichero_server.llm.get_api_key", lambda provider: provider_keys.supplied_api_key(provider))
    seen = []

    def refusing(url):
        seen.append(url)
        return False

    def account(listed, provider):
        return next(p["account"] for p in listed if p["provider"] == provider)

    provider_keys.forget_api_key("anthropic")
    listed = activity_models.places(probe=refusing)
    assert account(listed, "studio.example") == "not-reachable" and seen == ["http://studio.example:11434"]
    assert account(listed, "Anthropic") == "needs-key"
    assert account(listed, "ACENET") is None, "what nothing probes is None, never Ready"
    assert account(listed, "This Mac") == "ready"
    provider_keys.supply_api_key("anthropic", "sk-ant-test")
    try:
        assert account(activity_models.places(probe=lambda url: True), "Anthropic") == "ready"
        assert account(activity_models.places(probe=lambda url: True), "studio.example") == "ready"
    finally:
        provider_keys.forget_api_key("anthropic")


def test_unload_idle_models_frees_the_idle_and_keeps_a_model_with_a_page_in_flight(client, db, monkeypatch):
    """`models.row.what-unloading-gives-back` (#4987, #4999): the route calls `release_idle_models`, answers what it freed by
    name, and a Kraken reader with a page in flight is kept."""
    import sys
    import threading
    import types

    released = []
    runtime = types.SimpleNamespace(_RESIDENT={"catmus": object()}, _INFERENCE_LOCK=threading.Lock(),
                                    release_resident_models=lambda reason: released.append(reason))
    embeddings = types.SimpleNamespace(release_idle_embedders=lambda idle_seconds, reason: ["nomic-embed"])
    monkeypatch.setitem(sys.modules, "fichero_server.llm.kraken_runtime", runtime)
    monkeypatch.setitem(sys.modules, "fichero_server.db.embeddings", embeddings)
    monkeypatch.setattr(jobs, "_kraken_pages_in_flight", lambda: True)

    busy = client.post("/api/activity/models/unload-idle")
    assert busy.status_code == 200, busy.text
    assert busy.json()["freed"] == ["nomic-embed"] and released == [], "the idle embedder goes, the reading Kraken stays"

    monkeypatch.setattr(jobs, "_kraken_pages_in_flight", lambda: False)
    idle = client.post("/api/activity/models/unload-idle")
    assert idle.json()["freed"] == ["Kraken", "nomic-embed"] and released == ["memory is tight"]


def test_a_poll_checks_each_remote_mac_at_once_and_keeps_the_answer_for_a_while(app_db, monkeypatch):
    """The Models poll (every ten seconds) never waits on one Mac after another, and never re-checks an address inside its
    cache window (review of window-1)."""
    import threading
    import time

    import httpx
    from fichero_server.models import Provider, ProviderType

    for n in range(3):
        app_db.save_provider(Provider(id=f"p{n}", name=f"Mac{n}", provider_type=ProviderType("ollama"),
                                      api_base=f"http://mac{n}.example:11434"))
    calls = []
    gate = threading.Barrier(3, timeout=5)

    def slow_get(url, timeout):
        calls.append(url)
        gate.wait()  # all three must be in flight together, else the barrier times out
        raise httpx.ConnectError("asleep")

    monkeypatch.setattr(httpx, "get", slow_get)
    activity_models._reach_cache.clear()
    started = time.monotonic()
    listed = activity_models.places()
    assert [p["account"] for p in listed if p["place"] == "remote"] == ["not-reachable"] * 3
    assert len(calls) == 3 and time.monotonic() - started < 4
    activity_models.places()
    assert len(calls) == 3, "the second poll reads the cached answers"
    activity_models._reach_cache.clear()


def _entry(model_id, *, disk=None, weights=0, licence=None):
    from fichero_server.llm.local_model_facts import LocalModelCatalogEntry

    return LocalModelCatalogEntry(provider_type="omlx", model_id=model_id, display_name=model_id, installed=True,
                                  disk_usage_bytes=disk, download_size_bytes=weights, license_label=licence)


def test_an_installed_model_says_its_size_licence_and_whether_it_fits_with_memory_injected(db):
    """`models.window.one-list`, `models.row.fits-here` (#6588, #5221, #4987): size on disk and licence from the catalogue
    entry; "yes" under the comfortable share of the injected memory, "no" over its ceiling naming the loaded model whose
    unloading frees memory; "—" (None) for what nothing measures."""
    jobs._ensure(db)
    gib = 2**30
    installed = [("MLX", "small", _entry("small", disk=gib, weights=gib, licence="Apache-2.0")),
                 ("MLX", "huge", _entry("huge", disk=40 * gib, weights=40 * gib)),
                 ("MLX", "unsized", _entry("unsized"))]
    held = [{"name": "nomic-embed", "kind": "search embedder", "memory_bytes": 3 * gib}]

    found = {m["name"]: m for m in activity_models.models(db, held=held, installed=installed, physical_memory=16 * gib)}

    assert found["small"]["size_bytes"] == gib and found["small"]["licence"] == "Apache-2.0"
    assert found["small"]["fits_here"] == "yes" and found["small"]["needs_bytes"] > gib
    assert found["huge"]["fits_here"] == "no" and found["huge"]["fits_note"]
    assert found["huge"]["unload_to_fit"] == ["nomic-embed"]
    assert found["unsized"]["fits_here"] is None and found["unsized"]["size_bytes"] is None
    assert found["nomic-embed"]["fits_here"] is None, "a model nothing sizes is not guessed"


def test_a_failure_today_and_the_work_in_flight_ride_on_the_model(db):
    """`models.row.using-now-and-last-failed` (#6588, #6354): the newest failed job's row words and its fix button sit on
    its model; the kinds of the jobs running on it are `using_now`; a model with neither says so with null and []."""
    jobs._ensure(db)
    _job(db, "f0", kind="kraken-lines", model="kraken:blla", state="failed", minutes_ago=30)
    _job(db, "f1", kind="kraken-lines", model="kraken:blla", state="failed", minutes_ago=10)
    db.execute("UPDATE jobs SET reason = 'No credit at the provider' WHERE id = 'f0'")
    db.execute("UPDATE jobs SET reason = ? WHERE id = 'f1'", ["Model failed to load"])
    _job(db, "r1", kind="describe", model="anthropic:claude-sonnet", state="running")

    found = {m["name"]: m for m in activity_models.models(db, held=[], installed=[])}

    failed = found["blla"]["last_failed"]
    assert failed["words"] == "Model failed to load", "the newest failure, not the first"
    assert set(failed) == {"words", "kind", "button", "at"}
    assert found["blla"]["using_now"] == []
    assert found["claude-sonnet"]["using_now"] == ["describe"] and found["claude-sonnet"]["last_failed"] is None


def test_a_cloud_model_carries_its_places_account(db):
    """`models.row.account-from-a-probe` (#6588): a cloud model's Account is its provider row's, from the one probe."""
    jobs._ensure(db)
    call = {"provider": "anthropic", "model": "claude-sonnet", "place": "provider", "input_tokens": 1, "output_tokens": 1}
    _job(db, "c1", kind="describe", model="anthropic:claude-sonnet", state="done", detail=json.dumps({"usage": [call]}))
    accounts = {("cloud", "Anthropic"): "needs-key"}

    found = {m["name"]: m for m in activity_models.models(db, held=[], installed=[], accounts=accounts)}
    assert found["claude-sonnet"]["account"] == "needs-key"
    plain = {m["name"]: m for m in activity_models.models(db, held=[], installed=[])}
    assert plain["claude-sonnet"]["account"] is None


def test_this_mac_names_its_gpu_or_says_it_is_not_measured(db):
    """`models.window.one-list`: This Mac's GPU, read once; None when nothing names it."""
    assert activity_models.this_mac(db, memory=(None, None), gpu="Apple M1 GPU")["gpu"] == "Apple M1 GPU"
    assert activity_models.this_mac(db, memory=(None, None), gpu="")["gpu"] is None


def test_the_route_answers_the_new_columns(client, db, monkeypatch):
    """The route's answer carries each new field (the schema keeps them), places' account reaching the model rows."""
    jobs._ensure(db)
    monkeypatch.setattr(activity_models, "installed_on_this_mac",
                        lambda: [("MLX", "small", _entry("small", disk=2**30, weights=2**30))])
    row = next(m for m in client.get("/api/activity/models").json()["models"] if m["name"] == "small")
    assert row["size_bytes"] == 2**30
    assert {"fits_here", "needs_bytes", "fits_note", "unload_to_fit", "account", "licence", "using_now",
            "last_failed"} <= set(row)
    assert "gpu" in client.get("/api/activity/models").json()["this_mac"]


def test_a_places_egress_comes_from_its_address_not_its_provider_type(app_db, monkeypatch):
    """`models.place.egress-from-the-address` (#5582): a server off this Mac is "your machine" whatever the runtime it
    speaks, a cloud provider is the provider's, a cluster the institution's, this Mac stays."""
    from fichero_server.models import Provider, ProviderType

    app_db.save_provider(Provider(id="p-remote", name="Studio", provider_type=ProviderType("ollama"),
                                  api_base="http://studio.example:11434"))
    app_db.save_provider(Provider(id="p-here", name="Local", provider_type=ProviderType("ollama"),
                                  api_base="http://localhost:11434"))
    app_db.save_provider(Provider(id="p-cloud", name="Claude", provider_type=ProviderType("anthropic")))
    app_db.set_setting("hpc.clusters", json.dumps({"acenet": {"cluster_id": "acenet", "name": "ACENET"}}))
    listed = activity_models.places(probe=lambda url: True)
    egress = {p["provider"]: p["egress"] for p in listed}
    assert egress["studio.example"] == "own-machine"
    assert egress["Anthropic"] == "provider"
    assert egress["ACENET"] == "institution"
    assert egress["This Mac"] == "this-mac"
    assert "Local" not in egress and "localhost" not in egress, "a server on this Mac is This Mac, not a place of its own"
