"""`models.bookmark.kept-not-added` (#5460, #6588): a found card is bookmarked, never "added". A bookmarked card outlives a
search that no longer finds it; a card a step uses refuses Remove Bookmark with the step named."""
from __future__ import annotations

import pytest
from fichero_server.recipes import discovery
from fichero_server.recipes.discovery import Card

REPO = "acme/old-hands-reader"
ES = frozenset({"es"})


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))


def _card(repo=REPO):
    return Card(id=f"mlx:hf/{repo}@main", pin={"hf": repo, "revision": "main"}, jobs=discovery.READER_JOBS,
                languages=frozenset({"es"}), scripts=None, material=frozenset(), source="hugging-face", note=repo, size_gb=2.0)


def test_a_bookmarked_card_outlives_a_search_that_no_longer_finds_it(store):
    discovery.keep_hub([_card()], ES)
    discovery.bookmark(REPO)

    discovery.keep_hub([_card("acme/other")], ES)  # the next search for the same languages does not find it

    assert REPO in discovery.cached_hub() and discovery.cached_hub()[REPO]["bookmarked"] is True
    assert discovery.cached_hub()["acme/other"].get("bookmarked") is None


def test_a_card_not_bookmarked_is_let_go_by_the_next_search(store):
    discovery.keep_hub([_card()], ES)
    discovery.keep_hub([_card("acme/other")], ES)
    assert REPO not in discovery.cached_hub()


def test_remove_bookmark_lets_go_unless_a_step_uses_the_card(store):
    discovery.keep_hub([_card()], ES)
    discovery.bookmark(REPO)
    recipe = {"overrides": [{"step": "read-lines", "scope": "project", "folder_id": None, "card": _card().id}]}

    with pytest.raises(discovery.BookmarkInUse) as refused:
        discovery.remove_bookmark(REPO, recipe)
    assert "read-lines" in str(refused.value) and discovery.cached_hub()[REPO]["bookmarked"] is True

    discovery.remove_bookmark(REPO, {"overrides": []})
    assert not discovery.cached_hub()[REPO].get("bookmarked")


def test_bookmarking_a_card_never_found_is_refused(store):
    with pytest.raises(KeyError):
        discovery.bookmark("acme/never-found")
