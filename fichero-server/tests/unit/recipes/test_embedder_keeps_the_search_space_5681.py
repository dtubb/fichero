"""`source.recipe.embedder-by-language` (#5681): the search step keeps the engine's embedding space, and an embedder
already on this Mac says so.

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY (2026-10-11, the MCP onboarding walk):
model_candidates for make-a-vector called e5-large and bge-m3 "Downloads when first used" while local_models_list
showed both installed, and assemble chose bge-m3 over e5-large, the current default, which would move a project's
vectors to another space without the explicit migration. Through the routes; only which embedders are on this
Mac is stubbed.
"""
from __future__ import annotations

import pytest

from fichero_server.db.embeddings import search_embedder

ANSWERS = {"purposes": ["search"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
           "mac_memory_gb": 32}


@pytest.fixture
def embedders_here(monkeypatch):
    """e5-large and bge-m3 are on this Mac, as local_models_list shows them."""
    here = {"intfloat/multilingual-e5-large", "BAAI/bge-m3"}
    monkeypatch.setattr("fichero_server.llm.local_models.embedding_model_installed",
                        lambda name: name in here, raising=False)
    return here


def _vector_step(client):
    r = client.post("/api/recipes/assemble", json=ANSWERS)
    assert r.status_code == 200, r.text
    return next(s for s in r.json()["steps"] if s["job"] == "make-a-vector")


def test_the_search_step_keeps_the_engines_space(client, with_material, embedders_here):
    assert _vector_step(client)["model"]["hf"].lower() == search_embedder().lower()


def test_the_candidates_rank_the_engines_space_first_and_say_it_is_here(client, embedders_here):
    r = client.get("/api/recipes/candidates", params={"job": "make-a-vector", "languages": "es",
                                                          "scripts": "Latn"})
    assert r.status_code == 200, r.text
    items = {i["pin"].get("hf", "").lower(): i for i in r.json()["items"]}
    e5 = items[search_embedder().lower()]
    assert e5["rule_rank"] == 1, [(k, v["rule_rank"]) for k, v in items.items()]
    for name in ("intfloat/multilingual-e5-large", "baai/bge-m3"):
        assert items[name]["installed"] is True and items[name]["availability"] == "installed", items[name]
