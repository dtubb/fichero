"""`ai.cloud.project-overrides-the-default` (#6348): the app's cloud switch is a default; a project's own answer wins, yes or no."""
from __future__ import annotations

import pytest

from fichero_server.llm import egress
from fichero_server.recipes import places
from fichero_server.recipes.project import write_project_setup


@pytest.fixture
def app_says(monkeypatch):
    def _set(*placed):
        monkeypatch.setattr(places, "get_places", lambda: list(placed) if placed else None)
    return _set


def test_app_off_and_project_yes_sends(app_says):
    app_says("this-mac")
    assert places.may_leave_to({"cloud_allowed": True}, "cloud")


def test_app_on_and_project_no_refuses(app_says):
    app_says("this-mac", "cloud")
    assert not places.may_leave_to({"cloud_allowed": False}, "cloud")


def test_no_answer_inherits_the_app_either_way(app_says):
    app_says("this-mac", "cloud")
    assert places.may_leave_to({}, "cloud")
    app_says("this-mac")
    assert not places.may_leave_to({}, "cloud")


def test_the_other_places_stay_capped_by_the_app(app_says):
    app_says("this-mac")
    assert not places.may_leave_to({"cloud_allowed": True}, "huggingface")
    assert not places.may_leave_to({"cloud_allowed": True}, "acenet")


def test_the_egress_gate_agrees(app_says, tmp_path):
    app_says("this-mac")
    write_project_setup(tmp_path, {"cloud_allowed": True}, None)
    assert egress.project_allows_leaving(str(tmp_path))
    app_says("this-mac", "cloud")
    other = tmp_path / "b"
    other.mkdir()
    write_project_setup(other, {"cloud_allowed": False}, None)
    assert not egress.project_allows_leaving(str(other))


def test_one_action_sets_yes_or_no_and_undo_restores(client, app_says):
    app_says("this-mac")
    assert client.put("/api/recipes/project", json={"answers": {"purposes": ["transcribe"]}, "recipe": None}).status_code == 200
    yes = client.post("/api/recipes/project/allow-cloud")  # no body: yes, as before
    assert yes.status_code == 200 and yes.json()["cloud_allowed"] is True
    no = client.post("/api/recipes/project/allow-cloud", json={"allowed": False})
    assert no.status_code == 200 and no.json()["cloud_allowed"] is False
    assert client.get("/api/recipes/project").json()["answers"]["cloud_allowed"] is False
    audit = client.get("/api/actions/audit").json()["items"][0]
    assert audit["action_name"] == "project.allow_cloud"
    assert client.post(f"/api/actions/audit/{audit['id']}/undo").status_code == 200
    assert client.get("/api/recipes/project").json()["answers"]["cloud_allowed"] is True
