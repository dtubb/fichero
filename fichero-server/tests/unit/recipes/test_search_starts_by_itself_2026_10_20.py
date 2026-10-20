"""`source.onboard.search-triggered`: once Set Up knows the script and the language, the model search starts by itself
(the project's own `find-models` job), with no press of Search Online; not without both, not offline, and a search that
cannot be queued never fails the save."""
from __future__ import annotations

import pytest

from fichero_server.recipes import discovery

ANSWERS = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
           "pages": 100}


@pytest.fixture
def searches(monkeypatch):
    seen = []
    monkeypatch.setattr(discovery, "search", lambda db, languages, job=None: seen.append(languages) or {})
    monkeypatch.setattr(discovery, "egress_allowed", lambda: True)
    return seen


def test_saving_the_languages_and_script_starts_the_search(client, searches):
    assert client.put("/api/recipes/project", json={"answers": ANSWERS}).status_code == 200
    assert searches == [frozenset({"es"})]


@pytest.mark.parametrize("answers", [{**ANSWERS, "scripts": []}, {**ANSWERS, "languages": []}])
def test_without_both_nothing_is_searched(client, searches, answers):
    assert client.put("/api/recipes/project", json={"answers": answers}).status_code == 200
    assert searches == []


def test_offline_nothing_is_searched(client, searches, monkeypatch):
    monkeypatch.setattr(discovery, "egress_allowed", lambda: False)
    assert client.put("/api/recipes/project", json={"answers": ANSWERS}).status_code == 200
    assert searches == []


def test_a_search_that_cannot_be_queued_does_not_fail_the_save(client, searches, monkeypatch):
    def boom(db, languages, job=None):
        raise RuntimeError("no lane")

    monkeypatch.setattr(discovery, "search", boom)
    assert client.put("/api/recipes/project", json={"answers": ANSWERS}).status_code == 200
