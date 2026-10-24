"""`source.onboard.new-project-inherits-the-cloud-setting`: a project that has not answered the cloud question for itself
starts from the app's own yes (Settings > AI, where models may run); a project that answered no stays no, since it may be
stricter than the app, never looser. The model-call gate, the plan and the saved setup agree on it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.llm.egress import project_allows_leaving
from fichero_server.recipes import places
from fichero_server.recipes.project import read_project_setup, write_project_setup


def _project(tmp_path: Path, answers: dict | None) -> Path:
    library = tmp_path / "p.fichero"
    library.mkdir()
    if answers is not None:
        write_project_setup(library, answers, None)
    return library


@pytest.fixture
def app_allows_cloud(monkeypatch):
    monkeypatch.setattr(places, "get_places", lambda: ["this-mac", "cloud"])


@pytest.fixture
def app_keeps_this_mac(monkeypatch):
    monkeypatch.setattr(places, "get_places", lambda: ["this-mac"])


def test_a_project_with_no_answer_inherits_the_apps_yes_everywhere(tmp_path, app_allows_cloud):
    assert places.may_leave_to({}, "cloud")
    assert project_allows_leaving(str(_project(tmp_path, None))), "no setup saved: a new project"
    (tmp_path / "a").mkdir()
    unanswered = _project(tmp_path / "a", {"purposes": ["transcribe"]})
    assert project_allows_leaving(str(unanswered)), "a setup with no cloud answer"
    assert read_project_setup(unanswered)["answers"]["cloud_allowed"] is True


def test_a_project_that_said_no_stays_no_under_an_app_yes(tmp_path, app_allows_cloud):
    assert not places.may_leave_to({"cloud_allowed": False}, "cloud")
    (tmp_path / "b").mkdir()
    library = _project(tmp_path / "b", {"purposes": ["transcribe"], "cloud_allowed": False})
    assert not project_allows_leaving(str(library))
    assert read_project_setup(library)["answers"]["cloud_allowed"] is False


def test_an_app_that_keeps_pages_on_this_mac_gives_nothing_to_inherit(tmp_path, app_keeps_this_mac):
    assert not places.may_leave_to({}, "cloud")
    assert not project_allows_leaving(str(_project(tmp_path, None)))


def test_an_app_that_has_not_answered_gives_nothing_to_inherit(tmp_path, monkeypatch):
    monkeypatch.setattr(places, "get_places", lambda: None)
    assert not places.inherits_cloud()
    assert not project_allows_leaving(str(_project(tmp_path, None)))
