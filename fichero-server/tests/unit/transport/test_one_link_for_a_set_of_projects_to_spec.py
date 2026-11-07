"""sharing.host.which-projects-dialog, the ruled sub-bullet (#6366): with Multi-user off, the which-projects dialog ends with ONE
pairing link that gives the paired device every checked project (`sharing.link-grants-its-project`, for a set).
"""

from fichero_server.security import authz
from tests.unit.security import test_sharing_probe_2026_10_01 as probe

harness = probe.harness
_clear_pairing_state = probe._clear_pairing_state


def _second_project(tmp_path):
    package = tmp_path / "Second.fichero"
    package.mkdir()
    (package / "fichero.duckdb").write_bytes(b"")
    return authz.normalize_library_path(str(package))


def _device_libraries(harness, paired):
    r = harness.remote().get("/api/authz/libraries", headers=probe._bearer(paired["device_token"]))
    assert r.status_code == 200, r.text
    return {item["library_path"] for item in r.json()["items"]}


def _mint(harness, body):
    minted = harness.client().post("/api/pair/code", json=body, headers={"Authorization": "Bearer " + harness.bootstrap})
    assert minted.status_code == 200, minted.text
    paired = harness.remote().post("/api/pair", json={"code": minted.json()["code"], "device_name": "Air"})
    assert paired.status_code == 200, paired.text
    return paired.json()


def test_one_link_gives_the_device_every_checked_project(harness, tmp_path):
    first = authz.normalize_library_path(harness.library)
    second = _second_project(tmp_path)
    paired = _mint(harness, {"library": first, "libraries": [second]})
    assert {first, second} <= _device_libraries(harness, paired)


def test_a_path_that_is_no_project_is_left_out(harness, tmp_path):
    first = authz.normalize_library_path(harness.library)
    ghost = str(tmp_path / "Nothing.fichero")
    paired = _mint(harness, {"library": first, "libraries": [ghost]})
    assert ghost not in _device_libraries(harness, paired)
