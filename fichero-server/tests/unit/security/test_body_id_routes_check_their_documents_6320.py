# ruff: noqa: F811  (a fixture imported from another test module and taken by name: the pattern test_share_scope_5967 uses)
"""Routes that take a document (or a claim resting on one) in the BODY: the read/write dependency sees only the path and query, so
each handler must check the document itself. One denial test per route, through the real stack with multi-user on, for the two
callers that got through: an editor with a DENY on the folder, and a person shared one folder who puts a decoy id in the query
(#6320)."""

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.models import KnowledgeClaim
from fichero_server.security import authz
from tests.unit.security.test_sharing_probe_2026_10_01 import _multiuser_on, harness  # noqa: F401
from tests.unit.transport.test_person_bound_invite_5910 import _as
from tests.unit.transport.test_share_scope_5967 import _person, project  # noqa: F401


@pytest.fixture
def claim_on_b(project):
    db = db_manager.get_database(project.harness.library)
    claim = KnowledgeClaim(text="SECRET on B", source_document_id=project.ids["b1"], subject_canonical="Ann", predicate_verb="owned",
                           object_phrase="a house", source_excerpt="SECRET on B")
    db.save(claim)
    return claim


@pytest.fixture
def callers(project):
    """(client, decoy suffix) for: alice (editor) with a deny on B, and carla (scoped to A) with a decoy A id in the query."""
    alice = project.users["alice"]
    project.harness.app_db.set_library_acl_override(
        user_id=alice.id, library_path=authz.normalize_library_path(project.library), target_id=project.ids["B"], effect="deny")
    _person(project.harness, "carla")
    authz.grant_folder(actor=project.users["owner"], library=project.library, user="carla", folder_id=project.ids["A"], role="editor")
    return [(_as(project.harness, "alice"), ""), (_as(project.harness, "carla"), f"?x_id={project.ids['A']}")]


def _every_caller_refused(callers, path, body):
    for client, decoy in callers:
        got = client.post(path + decoy, json=body)
        assert got.status_code == 403, (path, decoy, got.status_code, got.text[:200])
    return True


def test_crop(project, callers):
    assert _every_caller_refused(callers, "/api/annotations/crop", {"document_id": project.ids["b1"], "kind": "highlight"})


def test_dataset_query_of_a_denied_folder_and_of_the_whole_project(project, callers):
    assert _every_caller_refused(callers, "/api/documents/dataset/query", {"parent_id": project.ids["B"], "recursive": True})
    assert _every_caller_refused(callers, "/api/documents/dataset/query", {})


def test_render_paragraph(project, callers, claim_on_b):
    assert _every_caller_refused(callers, "/api/kg/render/paragraph", {"claim_ids": [claim_on_b.id]})


def test_resolve_source_by_claim_and_by_triple(project, callers, claim_on_b):
    assert _every_caller_refused(callers, "/api/claims/resolve-source", {"claim_id": claim_on_b.id})
    assert _every_caller_refused(callers, "/api/claims/resolve-source",
                          {"subject_canonical": "Ann", "predicate_verb": "owned", "object_phrase": "a house"})


def test_assign_time_period_writes_nothing_to_a_denied_page(project, callers, claim_on_b):
    body = {"source_document_id": project.ids["b1"], "time_start": "1800"}
    assert _every_caller_refused(callers, "/api/claims/assign-time-period", body)
    assert _every_caller_refused(callers, "/api/claims/assign-time-period-from-metadata", {"source_document_id": project.ids["b1"]})
    assert db_manager.get_database(project.harness.library).get(KnowledgeClaim, claim_on_b.id).time_start is None


def test_locations_resolve(project, callers):
    assert _every_caller_refused(callers, "/api/locations/resolve", {"documentId": project.ids["b1"]})


def test_adding_a_denied_document_to_a_project(project, callers):
    from fichero_server.models.knowledge import Project

    db = db_manager.get_database(project.harness.library)
    shared = Project(name="Mine")
    db.save(shared)
    assert _every_caller_refused(callers, f"/api/projects/{shared.id}/include", {"target_id": project.ids["b1"], "target_type": "document"})


def test_library_item_columns(project, callers):
    assert _every_caller_refused(callers, "/api/library-items/columns", {"item_ids": [project.ids["b1"]]})
    assert _every_caller_refused(callers, "/api/library-items/columns", {"item_ids": [project.ids["B"]], "include_descendants": True})


def test_compare_vision_workflow_and_node_of_a_denied_page(project, callers):
    b1 = project.ids["b1"]
    assert _every_caller_refused(callers, "/api/model-comparison/compare-vision", {"models": [], "doc_ids": [b1]})
    assert _every_caller_refused(callers, "/api/model-comparison/compare-workflow", {"doc_id": b1, "workflow_id": "x", "models": []})
    assert _every_caller_refused(callers, "/api/model-comparison/compare-node", {"workflow_id": "x", "node_id": "n", "models": [], "inputs": {"selected_doc_ids": [b1]}})


def test_estimate_cost_chat_and_extract_text_of_a_denied_page(project, callers):
    b1 = project.ids["b1"]
    assert _every_caller_refused(callers, "/api/workflows/x/estimate-cost", {"selected_doc_ids": [b1]})
    assert _every_caller_refused(callers, "/api/chat", {"message": "hi", "document_ids": [b1]})
    assert _every_caller_refused(callers, "/api/chat/extract-text", {"document_ids": [b1]})


def test_browser_save_into_a_denied_folder(project, callers):
    assert _every_caller_refused(callers, "/api/research/tools/browser-save", {"url": "https://example.org/a.pdf", "project_id": "p", "parent_folder_id": project.ids["B"]})


def test_running_a_workflow_or_a_batch_on_a_denied_page(project, callers):
    b1 = project.ids["b1"]
    assert _every_caller_refused(callers, "/api/workflow-execution/execute", {"workflow_id": "x", "inputs": {"selected_doc_ids": [b1]}})
    assert _every_caller_refused(callers, "/api/batches", {"workflow_id": "x", "items": [{"doc_id": b1}]})


def test_a_kept_workbook_export_writes_the_whole_project_so_a_denied_page_anywhere_refuses_it(project, callers, tmp_path):
    """The kept export is the WHOLE project's work in a folder: a write check on the body's (readable) folder is not enough."""
    from fichero_server.kept_export import keep

    (tmp_path / "out").mkdir()
    kept = keep(db_manager.get_database(project.harness.library), str(tmp_path / "out"), "catalogue-workbook", "document")
    assert _every_caller_refused(callers, "/api/export/catalogue-workbook", {"target_id": project.ids["A"], "kept_export_id": kept})


def test_an_export_walks_the_tree_the_check_walks_a_page_under_a_trashed_folder_is_in_neither(project):
    """The check (`folder_scope`) stops at a trashed folder; the export must too, or a live page under it is read unchecked."""
    from fichero_server.core.timeutil import utc_now
    from fichero_server.export_service import _collect_documents
    from fichero_server.models import DocType, Document

    db = db_manager.get_database(project.harness.library)
    trashed = Document(name="gone", doc_type=DocType.folder, parent_id=project.ids["A"], deleted_at=utc_now())
    db.save(trashed)
    live = Document(name="live", doc_type=DocType.page, parent_id=trashed.id)
    db.save(live)
    assert live.id not in {d.id for d in _collect_documents(db, target_id=project.ids["A"], recursive=True)[1]}
