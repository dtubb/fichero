"""`models.bookmark.kept-not-added` and `models.search.is-the-finder` (#6588): a candidate says whether it is bookmarked and
under which key (so the Models window can draw the glyph and call the bookmark route), and a bookmarked card whose
search no longer finds it is still listed. Through `GET /api/recipes/candidates`; only the kept Hub list is seeded."""
from __future__ import annotations

import pytest

from fichero_server.recipes import discovery
from fichero_server.recipes.discovery import Card
from tests.unit.recipes.test_recipe_execution_to_spec import engine  # noqa: F401  (fixture)

REPO = "acme/old-hands-reader"
DE = frozenset({"de"})


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    monkeypatch.setattr(discovery, "_harvest", lambda: {})


def _card(repo=REPO):
    return Card(id=f"mlx:hf/{repo}@main", pin={"hf": repo, "revision": "main"}, jobs=discovery.READER_JOBS,
                languages=DE, scripts=None, material=frozenset(), source="hugging-face", note=repo, size_gb=2.0)


def _hub_items(client) -> dict:
    r = client.get("/api/recipes/candidates", params={"scripts": "Latf", "languages": "de"})
    assert r.status_code == 200, r.text
    return {c["pin"]["hf"]: c for c in r.json()["items"] if c["source"] == "hugging-face"}


def test_a_candidate_says_whether_it_is_bookmarked_and_its_key(client, store):
    discovery.keep_hub([_card(), _card("acme/other")], DE)
    discovery.bookmark(REPO)

    items = _hub_items(client)

    assert items[REPO]["bookmarked"] is True and items[REPO]["bookmark_key"] == REPO
    assert items["acme/other"]["bookmarked"] is False and items["acme/other"]["bookmark_key"] == "acme/other"


def test_a_bookmarked_card_no_search_finds_any_more_is_still_listed(client, store):
    discovery.keep_hub([_card()], DE)
    discovery.bookmark(REPO)
    discovery.keep_hub([_card("acme/other")], DE)  # the next search does not find it: found_for is now empty

    items = _hub_items(client)

    assert REPO in items and items[REPO]["bookmarked"] is True
    discovery.remove_bookmark(REPO, {"overrides": []})
    assert REPO not in _hub_items(client)
