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
    assert answer.json()["places"][0] == {"place": "this-mac", "provider": "This Mac"}


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
