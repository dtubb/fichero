"""`models.bookmark.kept-not-added` (#5460, #6588): the routes that keep a found card and let it go."""
from __future__ import annotations

import pytest
from fichero_server.recipes import discovery
from fichero_server.recipes.discovery import Card

REPO = "acme/old-hands-reader"
ES = frozenset({"es"})


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    discovery.keep_hub([Card(id=f"mlx:hf/{REPO}@main", pin={"hf": REPO, "revision": "main"}, jobs=discovery.READER_JOBS,
                             languages=frozenset({"es"}), scripts=None, material=frozenset(), source="hugging-face",
                             note=REPO, size_gb=2.0)], ES)


def test_a_found_card_is_bookmarked_and_let_go_through_the_routes(client, store):
    kept = client.post("/api/recipes/candidates/bookmark", json={"key": REPO})
    assert kept.status_code == 200, kept.text
    assert discovery.cached_hub()[REPO]["bookmarked"] is True

    gone = client.request("DELETE", "/api/recipes/candidates/bookmark", json={"key": REPO})
    assert gone.status_code == 200, gone.text
    assert "bookmarked" not in discovery.cached_hub()[REPO]


def test_a_card_no_search_found_is_refused_in_words(client, store):
    for method in ("POST", "DELETE"):
        refused = client.request(method, "/api/recipes/candidates/bookmark", json={"key": "nobody/nothing"})
        assert refused.status_code == 404 and "nobody/nothing" in refused.json()["detail"]
