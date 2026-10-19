"""#5828 (#5810's engine half): the places models may run are an app setting that caps every project, at USE.

WHY: Set Up Fichero's words promise "Your pages never leave this Mac" and "You can change this later". The answer lives
in the engine, set by an audited action. A project may be stricter, never looser; the cap is checked where pages would
leave, per place, and NO save may narrow a stored answer (review 213: choose_font and five more paths read the setup and
save it back).
"""
from __future__ import annotations

from fichero_server.models import ActionAudit
from fichero_server.recipes import answers as answers_mod
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


def test_a_save_never_narrows_what_the_project_stored(client, app_db):
    """The app is at this Mac only; choose_font reads the setup and saves it back: cloud_allowed stays true."""
    r = client.put("/api/recipes/project", json={"answers": {"cloud_allowed": True}})
    assert r.status_code == 200, r.text
    assert client.put("/api/recipes/font", json={"script": "Latn", "font": None}).status_code in (200, 422)
    assert client.get("/api/recipes/project").json()["answers"]["cloud_allowed"] is True


def test_reading_the_setup_never_caps_it(app_db, tmp_path):
    write_project_setup(tmp_path, {"cloud_allowed": True}, None)
    assert places.get_places() == ["this-mac"]
    assert read_project_setup(tmp_path)["answers"]["cloud_allowed"] is True


def test_pages_go_to_a_place_only_when_the_project_said_yes_and_the_app_allows_that_place(app_db):
    yes, no = {"cloud_allowed": True}, {"cloud_allowed": False}
    assert not places.may_leave_to(yes, "cloud"), "this Mac only"
    places.set_places(["cloud"])
    assert places.may_leave_to(yes, "cloud")
    assert not places.may_leave_to(no, "cloud"), "a stricter project is never loosened"
    assert not places.may_leave_to(yes, "huggingface") and not places.may_leave_to(yes, "acenet")


def test_allowing_only_another_mac_opens_neither_the_cloud_nor_hugging_face_nor_the_cluster(app_db):
    places.set_places(["another-mac"])
    yes = {"cloud_allowed": True}
    assert places.allows("another-mac")
    for place in ("cloud", "huggingface", "acenet"):
        assert not places.may_leave_to(yes, place), place


def test_copies_stay_on_the_cluster_needs_the_cluster_allowed_even_when_said_true(app_db):
    said = {"cloud_allowed": True, answers_mod.COPIES_STAY: True}
    assert not answers_mod.copies_may_stay(said)
    places.set_places(["acenet"])
    assert answers_mod.copies_may_stay(said)


def test_this_macs_line_is_worked_out_from_its_memory():
    assert "16 GB of memory: enough for the models made for your script, but not the largest AI models." in places.this_mac_line(16)
    small = places.this_mac_line(8)
    assert "8 GB of memory: enough for Kraken and Apple Vision, but too little for larger models." in small
    assert "allow another Mac, the cloud, or a cluster below" in small


def test_the_places_view_carries_the_machines_line(client, app_db):
    body = client.get("/api/recipes/places").json()
    assert body["memory_gb"] > 0 and body["this_mac"].startswith("This Mac has ")
