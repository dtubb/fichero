"""sharing.link-grants-its-project (#6359): a pairing link minted for a project reaches that project on the paired device.

The 2026-11-05 failure: a link minted for a project the app made on first run (never put in the known-library registry)
paired, then the guest's library list came back without it, and the guest said "didn't give this device that project".
"""

from tests.signed_in import signed_in_client
from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _bearer,
    _multiuser_on,
    harness,
)


def _device_libraries(harness, paired):  # noqa: F811
    r = harness.remote().get("/api/authz/libraries", headers=_bearer(paired["device_token"]))
    assert r.status_code == 200, r.text
    return {item["library_path"] for item in r.json()["items"]}


def test_a_device_paired_by_a_link_for_a_project_is_given_that_project(harness, monkeypatch):  # noqa: F811
    from fichero_server.api.routes.library.registry import get_global_database
    from fichero_server.models import KnownLibrary
    from fichero_server.security import authz

    path = authz.normalize_library_path(harness.library)
    registry = get_global_database()
    for row in registry.query(KnownLibrary, path=path):
        registry.delete(row)  # the project the app made on first run: never put in the registry
    assert not registry.query(KnownLibrary, path=path)

    users = _multiuser_on(harness, monkeypatch)
    owner = users["owner"]
    minter = signed_in_client(harness, owner)
    paired = harness.pair(harness.client(), code_headers=minter.headers)

    assert path in _device_libraries(harness, paired)
