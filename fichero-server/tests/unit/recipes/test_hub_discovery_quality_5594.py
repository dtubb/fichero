"""What the online model search finds, and how it runs (#5594), tested to the spec
(docs/contributor_manual/specs/source/models-chains-and-projects.md, "Finding models": `source.find.hub-readers-only`,
`source.find.unknown-size-said`, `source.find.reason-names-fit`, `source.find.online-search-is-a-job`).

WHY: the esoteric-languages run of 2026-10-07. For German and Japanese the Hugging Face source listed 31-34 builds,
among them 'uncensored', 'abliterated' and 'Heretic' chat models that read no page; every size said 0.0 GB; a Fraktur
project's reason said only "tagged de". And the first online call timed out at the CLI after 65 s (a repeat took 5 s):
the search ran inside the request.

Through the routes the app and MCP call (`GET /api/recipes/candidates`, `GET /api/activity/jobs`). The Hub and
Kraken's repository are stubbed; nothing reaches the network.
"""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.execution import jobs
from fichero_server.recipes import discovery

OCR = {"modelId": "someone/fraktur-ocr-mlx", "pipeline_tag": "image-to-text", "library_name": "mlx",
       "tags": ["mlx", "safetensors", "ocr", "fraktur", "image-to-text", "de", "license:apache-2.0"]}
VLM_OCR = {"modelId": "someone/Doc-VL-OCR-4bit", "pipeline_tag": "image-text-to-text", "library_name": "mlx",
           "tags": ["mlx", "safetensors", "qwen2_5_vl", "ocr", "document-understanding", "image-text-to-text",
                    "conversational", "de", "en", "license:apache-2.0"]}
CHAT = {"modelId": "TheCluster/Qwen3.5-9B-abliterated-MLX-4bit", "pipeline_tag": "image-text-to-text",
        "library_name": "mlx", "tags": ["mlx", "safetensors", "qwen3_5", "abliterated", "uncensored",
                                        "image-text-to-text", "conversational", "de", "en"]}


@pytest.fixture
def store(tmp_path, monkeypatch):
    """An empty model store of the test's own, an engine allowed to reach the network, and Kraken's repository
    stubbed as an empty listing."""
    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    monkeypatch.delenv("FICHERO_KRAKEN_DATA_DIR", raising=False)
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "0")
    monkeypatch.setattr(discovery, "_harvest", lambda: {})
    return get_mlx_model_store()


@pytest.fixture
def hub(monkeypatch):
    """The Hub's answer for German MLX builds: an OCR model, a vision-language model tagged OCR, and an abliterated
    chat model; every other query finds nothing. `hub.answer` holds every answer until the test lets it go."""
    asked: list[str] = []
    answer = threading.Event()
    answer.set()

    async def fetch(task=None, search=None, sort="downloads", limit=20, offset=0, library=None, tags=None):
        answer.wait(30)
        key = f"{task or ''}|{','.join(tags or [])}"
        asked.append(key)
        if key == "image-to-text|mlx,de":
            return [dict(OCR)]
        if key == "image-text-to-text|mlx,de":
            return [dict(VLM_OCR), dict(CHAT)]
        return []

    monkeypatch.setattr("fichero_server.api.routes.ai.models._fetch_hf_models", fetch)
    fetch.asked, fetch.answer = asked, answer
    yield fetch
    answer.set()  # never leave the job's thread waiting


def _candidates(client, **params) -> dict:
    r = client.get("/api/recipes/candidates", params={"scripts": "Latf", "languages": "de", "mac_memory_gb": 32,
                                                      **params})
    assert r.status_code == 200, r.text
    return r.json()


def _wait_for(db, job_id: str) -> dict:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        row = jobs.find_jobs(db, kinds=[discovery.SEARCH_KIND], job_id=job_id)[0]
        if row["state"] in ("done", "failed"):
            return row
        time.sleep(0.05)
    pytest.fail(f"the search job {job_id} did not finish")


def _searched(client, db, **params) -> dict:
    """An online listing as a person gets it: the call starts the search, and the call after it is done."""
    first = _candidates(client, online="true", **params)
    _wait_for(db, first["search_job"]["id"])
    return _candidates(client, online="true", **params)


def _hub_items(body: dict) -> dict:
    return {c["pin"]["hf"]: c for c in body["items"] if c["source"] == "hugging-face"}


def _source(body: dict, name: str) -> dict:
    return next(s for s in body["sources"] if s["source"] == name)


# --- source.find.hub-readers-only / unknown-size-said / reason-names-fit -------------------------------------


def test_source_find_hub_readers_only_a_chat_build_is_left_out_and_counted(client, db, store, hub):
    """source.find.hub-readers-only: "a Hugging Face result is a reader candidate only when its listing says it reads
    text from images … A chat build … is never listed, whatever its task; how many were left out is counted.\""""
    body = _searched(client, db)

    found = _hub_items(body)
    assert set(found) == {OCR["modelId"], VLM_OCR["modelId"]}
    hf = _source(body, "hugging-face")
    assert hf["state"] == "searched" and hf["count"] == 2 and hf["left_out"] == 1
    assert "1 build left out: chat models, not readers" in hf["detail"]
    assert not any("abliterated" in c["id"].lower() for c in body["items"])
    # The kept list obeys the same rule: the offline call afterwards lists the same two, and says one was left out.
    again = _candidates(client)
    assert set(_hub_items(again)) == set(found) and _source(again, "hugging-face")["left_out"] == 1


def test_source_find_unknown_size_said_never_zero(client, db, store, hub):
    """source.find.unknown-size-said: "a candidate whose size or memory its listing does not state says 'size not
    stated' … never 0.0 GB.\""""
    for card in _hub_items(_searched(client, db)).values():
        assert card["size"] == "size not stated" and card["size_gb"] is None and card["memory_gb"] is None
    shipped = [c for c in _candidates(client)["items"] if c["source"] == "shipped" and c["size_gb"]]
    assert shipped and all(c["size"].endswith(" GB") for c in shipped)


def test_source_find_reason_names_fit_script_language_and_how_it_runs(client, db, store, hub):
    """source.find.reason-names-fit: "a found reader's reason says why it fits the project in words: what it reads
    … a script such as Fraktur where its tags or name say so, the project's languages it lists by name, and that it
    is an MLX build this Mac runs; never only 'tagged de'.\""""
    found = _hub_items(_searched(client, db))
    fraktur = found[OCR["modelId"]]
    assert "OCR model" in fraktur["offered_because"] and "made for Latin (Fraktur variant)" in fraktur["offered_because"]
    assert "lists German" in fraktur["offered_because"] and "runs on this Mac" in fraktur["offered_because"]
    assert "Latf" in fraktur["scripts"]
    vlm = found[VLM_OCR["modelId"]]
    assert "vision-language model made for OCR" in vlm["offered_because"] and "lists German" in vlm["offered_because"]
    assert all("tagged" not in c["offered_because"] for c in found.values())


def test_the_reader_rule_reads_the_listing_alone():
    assert discovery.reads_text(OCR) and discovery.reads_text(VLM_OCR)
    assert discovery.reads_text(CHAT) is None
    plain_chat = {"modelId": "x/Mistral-Small-MLX", "pipeline_tag": "image-text-to-text", "tags": ["mlx"]}
    assert discovery.reads_text(plain_chat) is None  # a vision chat model with no OCR use
    heretic_ocr = {"modelId": "x/Heretic-OCR", "pipeline_tag": "image-to-text", "tags": ["mlx", "ocr"]}
    assert discovery.reads_text(heretic_ocr) is None  # a chat build whatever it claims
    captioner = {"modelId": "x/blip", "pipeline_tag": "image-to-text", "tags": ["image-captioning"]}
    assert discovery.reads_text(captioner) is None


# --- source.find.online-search-is-a-job ---------------------------------------------------------------------


def test_source_find_online_search_is_a_job_the_cold_call_answers_at_once(client, db, store, hub):
    """source.find.online-search-is-a-job: "`GET /api/recipes/candidates?online=true` answers at once with what is
    cached and the job … a later call returns the fresh list with the job done.\""""
    hub.answer.clear()  # the Hub does not answer until the test says so
    started = time.monotonic()
    cold = _candidates(client, online="true")
    assert time.monotonic() - started < 10, "the call waited for the Hub"
    job = cold["search_job"]
    assert job["id"] and job["state"] in ("waiting", "running")
    assert not _hub_items(cold)
    assert _source(cold, "hugging-face")["state"] == "searching"
    assert job["id"] in _source(cold, "hugging-face")["detail"]

    # Activity lists it, by name, while it runs.
    listed = client.get("/api/activity/jobs")
    assert listed.status_code == 200, listed.text
    row = next(j for j in listed.json()["jobs"] if j["id"] == job["id"])
    assert row["task_type"] == discovery.SEARCH_KIND and row["name"] == "Find reading models online"

    # A second call while it runs reuses it.
    assert _candidates(client, online="true")["search_job"]["id"] == job["id"]

    hub.answer.set()
    done = _wait_for(db, job["id"])
    assert done["state"] == "done" and '"hugging-face"' in done["detail"]  # its result is kept on the job
    fresh = _candidates(client, online="true")
    assert fresh["search_job"] == {"id": job["id"], "state": "done", "reason": None}
    assert set(_hub_items(fresh)) == {OCR["modelId"], VLM_OCR["modelId"]}
    assert _source(fresh, "hugging-face")["state"] == "searched"
    # Done within the day: not searched again.
    asked = list(hub.asked)
    assert _candidates(client, online="true")["search_job"]["id"] == job["id"] and hub.asked == asked


def test_with_no_project_open_the_online_search_is_not_run_and_says_why(client, store, hub):
    r = client.get("/api/recipes/candidates", params={"scripts": "Latf", "languages": "de", "online": "true"},
                   headers={"X-Fichero-Library-Path": ""})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["search_job"] is None and hub.asked == []
    assert _source(body, "hugging-face")["state"] == "not-searched"
    assert "open a project" in _source(body, "hugging-face")["detail"]


def test_working_offline_queues_no_search(client, db, store, hub, monkeypatch):
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")
    body = _candidates(client, online="true")
    assert body["search_job"] is None and _source(body, "hugging-face")["state"] == "offline"
    assert jobs.find_jobs(db, kinds=[discovery.SEARCH_KIND]) == []
