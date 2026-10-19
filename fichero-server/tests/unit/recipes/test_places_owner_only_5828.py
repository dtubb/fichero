"""#5828 review 224: where pages may go is the owner's to widen; a signed-in non-owner is refused, nothing changes."""
from fichero_server.recipes import places
from tests.signed_in import signed_in_client
from tests.unit.security.test_sharing_probe_2026_10_01 import _multiuser_on, harness  # noqa: F401


def test_a_signed_in_non_owner_cannot_widen_the_places(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    alice = signed_in_client(harness, users["alice"])
    r = harness.client().put("/api/recipes/places", json={"places": ["cloud"]}, headers=alice.headers)
    assert r.status_code == 403, r.text
    assert places.get_places() is None
    assert not [a for a in harness.app_db.list_action_audits() if a.action_name == "recipes.set_places"]


def test_the_owner_saves_and_the_chain_names_them(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    owner = signed_in_client(harness, users["owner"])
    r = harness.client().put("/api/recipes/places", json={"places": ["cloud"]}, headers=owner.headers)
    assert r.status_code == 200, r.text
    assert places.get_places() == ["this-mac", "cloud"]
    (row,) = [a for a in harness.app_db.list_action_audits() if a.action_name == "recipes.set_places"]
    assert row.actor == f"user:{users['owner'].id}"
