"""#5828 (#5810's engine half): the places models may run are an app setting that caps every project.

WHY: Set Up Fichero's words promise "Your pages never leave this Mac" and "You can change this later". The answer must
live in the engine, set by an audited action, and a project may be stricter, never looser (review 210).
"""
from __future__ import annotations

from fichero_server.models import ActionAudit
from fichero_server.recipes import places
from fichero_server.recipes.project import read_project_setup, write_project_setup


def test_this_mac_only_until_the_person_says_otherwise(client, app_db):
    r = client.get("/api/recipes/places")
    assert r.status_code == 200, r.text
    assert r.json()["places"] == ["this-mac"]


def test_the_answer_is_set_by_an_audited_action_and_this_mac_stays(client, app_db, db):
    r = client.put("/api/recipes/places", json={"places": ["cloud"]})
    assert r.status_code == 200, r.text
    assert r.json()["places"] == ["this-mac", "cloud"]
    assert client.get("/api/recipes/places").json()["places"] == ["this-mac", "cloud"]
    assert [a for a in db.query(ActionAudit) if a.action_name == "recipes.set_places"]


def test_an_unknown_place_is_refused_in_words(client, app_db):
    r = client.put("/api/recipes/places", json={"places": ["the-moon"]})
    assert r.status_code == 422 and "the-moon" in r.json()["detail"]


def test_a_project_saying_cloud_is_capped_while_only_this_mac_is_allowed(client, app_db, db, tmp_path):
    library = tmp_path
    write_project_setup(library, {"cloud_allowed": True}, None)
    assert read_project_setup(library)["answers"]["cloud_allowed"] is False, "capped by the app"
    assert read_project_setup(library, raw=True)["answers"]["cloud_allowed"] is True, "what the project saved"
    places.set_places(["cloud"])
    assert read_project_setup(library)["answers"]["cloud_allowed"] is True


def test_a_stricter_project_is_never_loosened(app_db, tmp_path):
    places.set_places(["cloud", "huggingface"])
    write_project_setup(tmp_path, {"cloud_allowed": False}, None)
    assert read_project_setup(tmp_path)["answers"]["cloud_allowed"] is False


def test_this_macs_line_is_worked_out_from_its_memory():
    assert "16 GB of memory: enough for the models made for your script, but not the largest AI models." in places.this_mac_line(16)
    small = places.this_mac_line(8)
    assert "8 GB of memory: enough for Kraken and Apple's text recognition, but too little for larger models." in small
    assert "allow another Mac, the cloud, or a cluster below" in small


def test_the_places_view_carries_the_machines_line(client, app_db):
    body = client.get("/api/recipes/places").json()
    assert body["memory_gb"] > 0 and body["this_mac"].startswith("This Mac has ")
