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
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)


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
    setup = read_project_setup(unanswered)
    assert setup["cloud_inherited"] is True and "cloud_allowed" not in setup["answers"], "beside the answers, never in them"


def test_a_project_that_said_no_stays_no_under_an_app_yes(tmp_path, app_allows_cloud):
    assert not places.may_leave_to({"cloud_allowed": False}, "cloud")
    (tmp_path / "b").mkdir()
    library = _project(tmp_path / "b", {"purposes": ["transcribe"], "cloud_allowed": False})
    assert not project_allows_leaving(str(library))
    setup = read_project_setup(library)
    assert setup["answers"]["cloud_allowed"] is False and setup["cloud_inherited"] is False


def test_an_app_that_keeps_pages_on_this_mac_gives_nothing_to_inherit(tmp_path, app_keeps_this_mac):
    assert not places.may_leave_to({}, "cloud")
    assert not project_allows_leaving(str(_project(tmp_path, None)))


def test_an_app_that_has_not_answered_gives_nothing_to_inherit(tmp_path, monkeypatch):
    monkeypatch.setattr(places, "get_places", lambda: None)
    assert not places.inherits_cloud()
    assert not project_allows_leaving(str(_project(tmp_path, None)))


def test_an_explicit_null_is_not_an_answer_to_inherit_from(tmp_path, app_allows_cloud):
    """Only a missing key is "has not answered": a null (or an odd value) is no, so nothing inherits into it."""
    assert not places.may_leave_to({"cloud_allowed": None}, "cloud")
    (tmp_path / "n").mkdir()
    assert not project_allows_leaving(str(_project(tmp_path / "n", {"purposes": ["transcribe"], "cloud_allowed": None})))


def test_a_save_through_use_candidate_leaves_the_cloud_answer_absent(client, with_material, mac, monkeypatch):  # noqa: F811
    """The inherited yes must not be written back: a save while the app is this-Mac-only would freeze the project closed, and a
    save while it allows the cloud would audit a yes nobody gave."""
    monkeypatch.setattr(places, "get_places", lambda: ["this-mac", "cloud"])
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
               "mac_memory_gb": 32}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200
    assert client.get("/api/recipes/project").json()["cloud_inherited"] is True
    used = client.post("/api/recipes/project/steps/use-candidate",
                       json={"step": "find-lines", "card": "apple:vision/find-lines@os"})
    assert used.status_code == 200, used.text
    saved = client.get("/api/recipes/project").json()
    assert "cloud_allowed" not in saved["answers"], "use-candidate wrote the inherited yes into the answers"
    assert saved["cloud_inherited"] is True
