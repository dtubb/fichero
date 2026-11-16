"""A registry that cannot be written refuses the redeem with a 503 and spends nothing (#6366): no swallowed failure."""

from fichero_server.api.routes.auth import pairing
from fichero_server.security import authz
from tests.unit.security import test_sharing_probe_2026_10_01 as probe

harness = probe.harness


def test_unwritable_registry_is_reported_to_the_caller(monkeypatch):
    class Broken:
        def query(self, *_a, **_k):
            raise OSError("read-only")

    monkeypatch.setattr("fichero_server.api.routes.library.registry.get_global_database", lambda: Broken())
    assert pairing._register_link_library("/tmp/Some Project") is False


def test_redeem_with_unwritable_registry_makes_no_device_and_keeps_the_code(harness, monkeypatch):
    minted = harness.client().post(
        "/api/pair/code", json={"library": authz.normalize_library_path(harness.library)}, headers={"Authorization": "Bearer " + harness.bootstrap}
    )
    assert minted.status_code == 200, minted.text
    code = minted.json()["code"]

    def broken():
        raise OSError("read-only")

    with monkeypatch.context() as broken_registry:
        broken_registry.setattr("fichero_server.api.routes.library.registry.get_global_database", broken)
        refused = harness.remote().post("/api/pair", json={"code": code, "device_name": "Air"})
    assert refused.status_code == 503
    assert harness.app_db.list_devices() == []
    # the code was not spent: the retry the 503 asks for pairs
    assert harness.remote().post("/api/pair", json={"code": code, "device_name": "Air"}).status_code == 200
