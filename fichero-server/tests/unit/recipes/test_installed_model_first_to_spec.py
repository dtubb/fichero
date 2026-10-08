"""A step's model that is not on this Mac never refuses Start in words the person must answer by editing the recipe
(#5583), tested to the spec (docs/contributor_manual/specs/source/models-chains-and-projects.md, section 7b's
"Everything automatic after Start": `source.onboard.auto.installed-model-first`).

WHY: onboarding run 2026-10-07 (Istmina box, local only). The first Start was refused, "steps correct cannot run on
this Mac: Qwen2.5-VL 7B (OCR) is not installed… choose an installed one: Qwen2.5-VL 3B", and the operator had to
hand-edit the recipe through save_project_setup and guess the model id. Through the public routes the app calls
(`POST /api/recipes/assemble`, `PUT /api/recipes/project`, `GET /api/recipes/project/start`,
`POST /api/recipes/project/start/use-instead`); only this Mac's model store (which models are installed) and its
memory are stubbed: nothing is downloaded or loaded.
"""
from __future__ import annotations

from typing import Any

import pytest

from fichero_server.llm.local_inference import LocalInferenceCapabilities
from fichero_server.llm.mlx_model_store import MLXModelStore
from tests.unit.recipes.test_recipe_execution_to_spec import _recipe, _save, engine, pages  # noqa: F401

SEVEN = {"hf": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit", "revision": "main"}
THREE_CARD = "mlx:hf/mlx-community/Qwen2.5-VL-3B-Instruct-4bit@unpinned"
LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}
READ = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}
CORRECT = {"id": "correct", "job": "correct", "model": SEVEN, "runs_on": "this-mac"}


class _Store(MLXModelStore):
    """The real store's catalogue and naming, with a stubbed set of installed models."""

    def __init__(self, root, installed: set[str]) -> None:
        super().__init__(root=root)
        self.installed = set(installed)

    def is_complete(self, spec: Any) -> bool:
        return spec.model_id in self.installed


@pytest.fixture
def mac(monkeypatch, tmp_path):
    """A 16 GB Apple-silicon Mac with no MLX model installed; `mac.store.installed` changes that."""
    from fichero_server.llm import local_model_choice

    store = _Store(tmp_path / "mlx", set())
    monkeypatch.setattr("fichero_server.llm.local_inference.get_local_inference_capabilities",
                        lambda: LocalInferenceCapabilities(system="Darwin", machine="arm64", is_apple_silicon=True,
                                                           physical_memory_bytes=16 * 1024**3,
                                                           macos_version="26.0"))
    monkeypatch.setattr("fichero_server.llm.mlx_model_store.get_mlx_model_store", lambda: store)
    monkeypatch.setattr(local_model_choice, "_store", lambda: store)
    return store


def test_source_onboard_auto_installed_model_first_at_start(client, db, pages, mac):
    """source.onboard.auto.installed-model-first (2): "When the plan's step is pinned to a catalogue MLX model that
    is not installed, the plan offers it in `downloads` … and, beside it, `instead`: every installed model this Mac
    can serve for that step … Start waits, saying so, until one is taken: the refusal names the download and the
    installed models, never 'edit the recipe'." Then one press uses the installed model, kept on the recipe."""
    mac.installed.add("Qwen2.5-VL-3B")
    _save(client, _recipe(None, LINES, READ, CORRECT), cloud_allowed=False)
    plan = client.get("/api/recipes/project/start").json()

    [download] = [d for d in plan["downloads"] if d["runtime"] == "mlx"]
    assert download["model"] == "Qwen2.5-VL-7B" and download["name"] == "Qwen2.5-VL 7B (OCR)"
    assert download["size_mb"] == 5653 and download["steps"] == ["correct"]
    assert download["action"] == "model.download" and download["params"] == {"runtime": "mlx",
                                                                                "model": "Qwen2.5-VL-7B"}
    assert download["instead"] == [{"card": THREE_CARD, "model": "Qwen2.5-VL-3B", "name": "Qwen2.5-VL 3B (OCR)",
                                    "licence": "Qwen-Research"}], "a licence that is not open is named: the press accepts it"
    [refusal] = plan["refusals"]
    assert "download it, or use the installed Qwen2.5-VL 3B (OCR) instead" in refusal
    assert "cannot run on this Mac" not in refusal and "Settings" not in refusal

    used = client.post("/api/recipes/project/start/use-instead",
                       json={"model": "Qwen2.5-VL-7B", "card": THREE_CARD})
    assert used.status_code == 200, used.text
    step = next(s for s in used.json()["recipe"]["steps"] if s["id"] == "correct")
    assert step["model"]["hf"] == "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"
    [override] = used.json()["recipe"]["overrides"]
    assert override["step"] == "correct" and override["scope"] == "project" and override["card"] == THREE_CARD
    assert "chosen by you" in override["because"]

    plan = client.get("/api/recipes/project/start").json()
    assert plan["refusals"] == [] and plan["downloads"] == []
    review = next(w for w in plan["workflows"] if w["steps"] == ["correct"])
    assert (review["provider_override"], review["model_override"]) == (
        "omlx", "mlx-community/Qwen2.5-VL-3B-Instruct-4bit")


def test_use_instead_refuses_a_choice_the_plan_does_not_offer(client, db, pages, mac):
    """Only an installed model the plan offers instead of a download it waits for is taken."""
    _save(client, _recipe(None, LINES, READ, CORRECT), cloud_allowed=False)
    plan = client.get("/api/recipes/project/start").json()
    [download] = [d for d in plan["downloads"] if d["runtime"] == "mlx"]
    assert download["instead"] == [], "nothing installed: only the download is offered"
    assert "download it (Set Up… › Ready)" in plan["refusals"][0]
    r = client.post("/api/recipes/project/start/use-instead", json={"model": "Qwen2.5-VL-7B", "card": THREE_CARD})
    assert r.status_code == 422 and "not an installed model offered instead" in r.json()["detail"]
    r = client.post("/api/recipes/project/start/use-instead", json={"model": "Chandra-OCR", "card": THREE_CARD})
    assert r.status_code == 422 and "not a model this project's Start waits to download" in r.json()["detail"]


def test_source_onboard_auto_installed_model_first_when_proposing(client, mac, monkeypatch):
    """source.onboard.auto.installed-model-first (1): "When the rules propose a recipe, a model already on this Mac
    wins over one that must be downloaded, among the cards the rules accept for the step, after accuracy … the
    reason says 'already on this Mac'." With the 3B's licence accepted (so the rules accept both Qwen cards for
    correcting), nothing installed proposes the smaller 3B, to download first; with only the 7B installed, the 7B
    wins although it is larger."""
    from dataclasses import replace

    from fichero_server.recipes import cards

    seed = cards.all_seed_cards()
    accepted = tuple(replace(c, open_licence=True) if c.id == THREE_CARD else c for c in seed)
    monkeypatch.setattr(cards, "all_seed_cards", lambda: accepted)
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
               "mac_memory_gb": 32}

    def proposed() -> dict:
        r = client.post("/api/recipes/assemble", json=answers)
        assert r.status_code == 200, r.text
        return next(s for s in r.json()["steps"] if s["job"] == "correct")

    step = proposed()
    assert step["model"]["hf"] == "mlx-community/Qwen2.5-VL-3B-Instruct-4bit", step["reasons"]
    assert any(r.startswith("to download first") for r in step["reasons"])

    mac.installed.add("Qwen2.5-VL-7B")
    step = proposed()
    assert step["model"]["hf"] == SEVEN["hf"], step["reasons"]
    assert "already on this Mac" in step["reasons"]


def _heard(queue, seconds: float = 10.0) -> list[Any]:
    """The change events a window subscribed with `queue` heard within `seconds`, once one arrives."""
    import time

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if not queue.empty():
            heard = []
            while not queue.empty():
                heard.append(queue.get_nowait())
            return heard
        time.sleep(0.05)
    return []


def test_source_onboard_auto_installed_model_first__the_plan_drops_a_finished_download(client, db, pages, mac,
                                                                                       monkeypatch):
    """source.onboard.auto.installed-model-first (#5583): "the plan re-reading itself when the MLX download
    finishes". Download, pressed in Ready (the plan's own `model.download` through the download route), fetches the
    model; when it is complete every window hears `model.installed` (its runtime and model), the cue to read the plan
    again, and the plan read again offers no download and refuses nothing: the refusal was only the download."""
    from fichero_server.api import change_stream as cs

    hub = cs._ChangeHub()
    monkeypatch.setattr(cs, "_change_hub", hub)
    window = hub.subscribe("/lib/window.fichero")

    async def fetched(job, spec):  # the fetch itself (a subprocess with the MLX runtime): the files arrive
        mac.installed.add(spec.model_id)
        job.state = "completed"

    monkeypatch.setattr(mac, "_run_download", fetched)
    _save(client, _recipe(None, LINES, READ, CORRECT), cloud_allowed=False)
    plan = client.get("/api/recipes/project/start").json()
    [download] = [d for d in plan["downloads"] if d["runtime"] == "mlx"]
    assert plan["refusals"], "Start waits for the download"

    params = download["params"]
    r = client.post(f"/api/local-models/download/{params['runtime']}/{params['model']}")
    assert r.status_code == 200, r.text

    heard = [e for e in _heard(window) if e.type == "model.installed"]
    assert [e.metadata for e in heard] == [{"runtime": "mlx", "model": "Qwen2.5-VL-7B"}], heard
    plan = client.get("/api/recipes/project/start").json()
    assert plan["downloads"] == [] and plan["refusals"] == [], plan
    assert next(w for w in plan["workflows"] if w["steps"] == ["correct"])["model_override"] == SEVEN["hf"]


def test_a_finished_download_model_job_says_so(monkeypatch):
    """The same word when a `download-model` job (a spaCy pipeline the plan waits for) finishes; none when it fails."""
    from fichero_server.api import change_stream as cs
    from fichero_server.llm import local_models

    hub = cs._ChangeHub()
    monkeypatch.setattr(cs, "_change_hub", hub)
    window = hub.subscribe("/lib/window.fichero")
    monkeypatch.setattr(local_models.LocalModelManager, "download_model", lambda self, runtime, name: None)
    local_models._run_download("spacy:es_core_news_md")
    [event] = _heard(window)
    assert (event.type, event.metadata) == ("model.installed", {"runtime": "spacy", "model": "es_core_news_md"})

    def broken(self, runtime, name):
        raise RuntimeError("the network went away")

    monkeypatch.setattr(local_models.LocalModelManager, "download_model", broken)
    with pytest.raises(RuntimeError):
        local_models._run_download("spacy:es_core_news_md")
    assert _heard(window, 0.3) == []
