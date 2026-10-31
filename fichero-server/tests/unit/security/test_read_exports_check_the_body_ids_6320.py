# ruff: noqa: F811  (a fixture imported from another test module and taken by name: the pattern test_share_scope_5967 uses)
"""The catalogue workbook and the batch-prepare preview are POSTs that only read, so they sit on the write-authz allowlist; the ids they
read arrive in the BODY, which the read dependency never looks at. A decoy id in the query used to stand in for them (#6320)."""

import pytest

from fichero_server.security import authz
from tests.unit.security.test_sharing_probe_2026_10_01 import _multiuser_on, harness  # noqa: F401
from tests.unit.transport.test_person_bound_invite_5910 import _as
from tests.unit.transport.test_share_scope_5967 import _person, project  # noqa: F401,F811

TURN = {"op": "rotate", "angle": 90}


def _routes(project):
    return "/api/export/catalogue-workbook", "/api/images/batch-prepare/preview"


@pytest.fixture
def scoped(project):
    _person(project.harness, "carla")
    authz.grant_folder(actor=project.users["owner"], library=project.library, user="carla", folder_id=project.ids["A"], role="viewer")
    workbook, preview = _routes(project)
    return project, _as(project.harness, "carla"), workbook, preview


def test_a_decoy_id_in_the_query_does_not_stand_in_for_the_body(scoped):
    project, client, workbook, preview = scoped
    a, b = project.ids["A"], project.ids["B"]
    assert client.post(workbook, json={}).status_code == 403  # the whole project: refused to a person shared one folder
    assert client.post(workbook + f"?target_id={a}", json={}).status_code == 403
    assert client.post(workbook + f"?target_id={a}", json={"target_id": b}).status_code == 403
    assert client.post(preview + f"?folder_id={a}", json={"folder_id": b, "operation": TURN}).status_code == 403
    assert client.post(preview, json={"folder_id": b, "operation": TURN}).status_code == 403


def test_a_person_still_reads_their_own_folder(scoped):
    """A person shared one folder names it in the query too (the read dependency refuses an id-less request to a scoped person)."""
    project, client, workbook, preview = scoped
    a = project.ids["A"]
    assert client.post(workbook + f"?target_id={a}", json={"target_id": a}).status_code != 403
    assert client.post(preview + f"?folder_id={a}", json={"folder_id": a, "operation": TURN}).status_code == 200


def test_a_project_viewer_denied_a_folder_cannot_read_it_through_either_route(project):
    bob = project.users["bob"]
    project.harness.app_db.set_library_acl_override(
        user_id=bob.id, library_path=authz.normalize_library_path(project.library), target_id=project.ids["B"], effect="deny")
    workbook, preview = _routes(project)
    client = _as(project.harness, "bob")
    assert client.post(workbook, json={"target_id": project.ids["B"]}).status_code == 403
    assert client.post(preview, json={"folder_id": project.ids["B"], "operation": TURN}).status_code == 403
    assert client.post(workbook, json={}).status_code == 403  # the whole project holds the denied folder


FILE_EXPORTS = ("excel", "jsonl", "parquet", "eleventy-site", "markdown-folder", "word")


def _deny(project, user, folder_key):
    project.harness.app_db.set_library_acl_override(
        user_id=user.id, library_path=authz.normalize_library_path(project.library), target_id=project.ids[folder_key], effect="deny")


@pytest.mark.parametrize("route", FILE_EXPORTS)
def test_the_file_exports_read_check_their_body_ids_too(project, route, tmp_path):
    """The same hole in the siblings that write a file: a decoy id in the query stood in for the body's `target_id`."""
    _person(project.harness, "carla")
    authz.grant_folder(actor=project.users["owner"], library=project.library, user="carla", folder_id=project.ids["A"], role="editor")
    client = _as(project.harness, "carla")
    out = str(tmp_path / f"out-{route}")
    a, b = project.ids["A"], project.ids["B"]
    assert client.post(f"/api/export/{route}?target_id={a}", json={"target_id": b, "output_path": out}).status_code == 403
    assert client.post(f"/api/export/{route}", json={"output_path": out}).status_code == 403  # the whole project
    # an EMPTY id is the whole project to the exporters: it must be checked as the whole project, with or without a decoy
    assert client.post(f"/api/export/{route}?target_id={a}", json={"target_id": "", "output_path": out}).status_code == 403
    assert client.post(f"/api/export/{route}", json={"target_id": "", "output_path": out}).status_code == 403


@pytest.mark.parametrize("route", FILE_EXPORTS)
def test_an_editor_with_a_deny_cannot_export_the_folder_or_the_whole_project(project, route, tmp_path):
    """alice edits the project (so the write dependency passes); a deny on folder B must still stop an export of B, of the
    whole project by omission and by an empty id, and of A's page denied inside A."""
    alice = project.users["alice"]
    _deny(project, alice, "B")
    client = _as(project.harness, "alice")
    out = str(tmp_path / f"out-{route}")
    for body in ({"target_id": project.ids["B"]}, {}, {"target_id": ""}):
        assert client.post(f"/api/export/{route}", json={**body, "output_path": out}).status_code == 403, body
    assert client.post(f"/api/export/{route}", json={"target_id": project.ids["A"], "output_path": out}).status_code != 403


@pytest.mark.parametrize("route", FILE_EXPORTS)
def test_a_page_denied_inside_a_readable_folder_stops_the_export_of_that_folder(project, route, tmp_path):
    alice = project.users["alice"]
    project.harness.app_db.set_library_acl_override(
        user_id=alice.id, library_path=authz.normalize_library_path(project.library), target_id=project.ids["a2"], effect="deny")
    out = str(tmp_path / f"out-{route}")
    got = _as(project.harness, "alice").post(f"/api/export/{route}", json={"target_id": project.ids["A"], "output_path": out})
    assert got.status_code == 403


def test_the_workbook_and_preview_refuse_an_empty_or_denied_id_to_a_viewer_with_a_deny(project):
    bob = project.users["bob"]
    _deny(project, bob, "B")
    workbook, preview = _routes(project)
    client = _as(project.harness, "bob")
    assert client.post(workbook, json={"target_id": ""}).status_code == 403
    assert client.post(workbook, json={}).status_code == 403
    assert client.post(preview, json={"folder_id": project.ids["B"], "operation": TURN}).status_code == 403
