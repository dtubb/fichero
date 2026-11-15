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


def test_each_model_is_placed_loaded_active_and_measured(db):
    jobs._ensure(db)
    _job(db, "k1", kind="kraken-lines", model="kraken:blla", state="running")
    _job(db, "k0", kind="kraken-lines", model="kraken:blla", state="done", minutes_ago=10)
    call = {"provider": "anthropic", "model": "claude-sonnet", "place": "provider", "input_tokens": 10, "output_tokens": 5}
    _job(db, "c1", kind="describe", model="anthropic:claude-sonnet", state="done", detail=json.dumps({"usage": [call, call]}))
    _job(db, "r1", kind="read-at-scale", model="trocr", state="done", target="acenet")
    held = [{"name": "nomic-embed", "kind": "search embedder", "memory_bytes": 312_000_000}]

    found = {(m["place"], m["provider"], m["name"]): m for m in activity_models.models(db, held=held)}

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


def test_the_route_answers_the_list(client, db):
    jobs._ensure(db)
    _job(db, "k1", kind="kraken-lines", model="kraken:blla", state="running")
    answer = client.get("/api/activity/models")
    assert answer.status_code == 200, answer.text
    assert any(m["provider"] == "Kraken" for m in answer.json()["models"])
