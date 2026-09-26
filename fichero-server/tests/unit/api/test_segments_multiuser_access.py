"""Issue #4917 (write side) — multi-user access must reach a document's
segments, passes and matches, not just the document row itself.

`ActionRegistry.invoke` checks `authz.assert_can_write` for every id
`authz.target_ids_from_params` finds in a segment action's params -- and
segment actions almost always name a SEGMENT or PASS id, never the
document. Before `security/authz.py`'s fix, `_target_ancestor_ids` only
knew how to walk a `Document`'s own ancestors: a non-document id fell
through to "itself only" (and a lookup error fell through the SAME way,
silently), so a deny/grant placed on the document (or a folder above it)
never reached its segments -- an editor denied a document could still
edit its segments by id.

Each test names the behaviour id it pins. Built from the router itself
(`_WRITE_ROUTE_CHECKS`), so a new write route either gets covered here or
fails `test_every_write_route_is_covered` for being unlisted.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document import segments as segments_route_module
from fichero_server.models import (
    Artifact,
    ContentRepresentation,
    ContentRepresentationKind,
    Document,
    DocType,
    Segment,
    SegmentMatch,
    SegmentPass,
    Status,
)
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import bbox_and_tile_from_anchor
from fichero_server.security import accounts, authz

pytestmark = pytest.mark.source_model


# ---------------------------------------------------------------------------
# Fixtures -- same shape as test_segments_route.py's, plus an editor.
# ---------------------------------------------------------------------------


@pytest.fixture
def users(app_db):
    owner = app_db.create_user(
        username="owner", display_name="Owner",
        password_hash=accounts.hash_password("password"), is_owner=True,
    )
    editor = app_db.create_user(
        username="editor", display_name="Editor",
        password_hash=accounts.hash_password("password"),
    )
    return SimpleNamespace(owner=owner, editor=editor)


def _grant_role(app_db, user, library_path: str, role: str) -> None:
    app_db.set_library_role(
        user_id=user.id, library_path=authz.normalize_library_path(library_path), role=role,
    )


def _override(app_db, user, library_path: str, target_id: str, effect: str) -> None:
    app_db.set_library_acl_override(
        user_id=user.id, library_path=authz.normalize_library_path(library_path),
        target_id=target_id, effect=effect,
    )


@pytest.fixture
def multiuser_client(test_package, app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")

    import fichero_server.api.main as api_main

    api_main = importlib.reload(api_main)
    client = TestClient(
        api_main.app,
        headers={"X-Fichero-Library-Path": quote(str(test_package), safe="/")},
    )

    def _login(username: str) -> dict[str, str]:
        response = client.post(
            "/api/auth/login", json={"username": username, "password": "password"},
        )
        assert response.status_code == 200
        token = response.json()["session_token"]
        return {"Authorization": f"Bearer {token}"}

    try:
        yield client, _login, str(test_package)
    finally:
        client.close()
        api_main.app.dependency_overrides.clear()
        monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
        importlib.reload(api_main)


def _make_doc(db, name: str) -> Document:
    doc = Document(
        name=name, doc_type=DocType.file, file_type=None,
        path=f"/{name}", status=Status.completed,
    )
    db.save(doc)
    return doc


def _make_pass(db, document_id: str) -> SegmentPass:
    pass_row = SegmentPass(document_id=document_id, name="p", provenance_kind=ProvenanceKind.workflow)
    db.save(pass_row)
    return pass_row


def _make_segment(db, *, document_id: str, pass_id: str, rect: list[float]) -> Segment:
    anchor = SourceAnchor(document_id=document_id, rect=rect)
    x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
    seg = Segment(
        document_id=document_id, pass_id=pass_id, kind="word", anchor=anchor,
        bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h, tile=tile,
        doc_kind=f"{document_id}:word", provenance_kind=ProvenanceKind.workflow,
    )
    db.save(seg)
    return seg


def _sys_ctx(db) -> ActionContext:
    """Pre-existing state, put there before the editor's own request
    arrives -- `is_bootstrap=True` bypasses authz for this SETUP step
    (same escape hatch a real bootstrap/import path uses), since "daniel"
    is not a registered, role-granted user in these multiuser-enabled
    test libraries and setup is not what any of these tests are about."""
    return ActionContext(actor="daniel", library_path=str(db.path.parent), is_bootstrap=True)


# ---------------------------------------------------------------------------
# One request builder per WRITE route in the segments router. Each builder
# takes (db, document_id), does whatever setup that route needs (a pass,
# live segments, a match at the right state), and returns (method, url,
# json) for a request that -- absent authz -- would succeed.
# ---------------------------------------------------------------------------


def _build_pass_create(db, doc_id):
    return "POST", "/api/segments/passes", {"document_id": doc_id, "name": "p"}


def _build_pass_delete(db, doc_id):
    pass_row = _make_pass(db, doc_id)
    return "DELETE", f"/api/segments/passes/{pass_row.id}", None


def _build_segment_create(db, doc_id):
    pass_row = _make_pass(db, doc_id)
    return "POST", "/api/segments", {
        "document_id": doc_id, "pass_id": pass_row.id, "kind": "word",
        "anchor": {"document_id": doc_id, "rect": [0.1, 0.1, 0.1, 0.1]},
    }


def _build_segment_bulk(db, doc_id):
    pass_row = _make_pass(db, doc_id)
    return "POST", "/api/segments/bulk", {
        "document_id": doc_id, "pass_id": pass_row.id,
        "segments": [{"kind": "word", "anchor": {"document_id": doc_id, "rect": [0.1, 0.1, 0.1, 0.1]}}],
    }


def _build_match_propose(db, doc_id):
    pass_row = _make_pass(db, doc_id)
    a = _make_segment(db, document_id=doc_id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
    b = _make_segment(db, document_id=doc_id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])
    return "POST", "/api/segments/matches", {"from_segment_id": a.id, "to_segment_id": b.id}


def _propose_match(db, doc_id):
    pass_row = _make_pass(db, doc_id)
    a = _make_segment(db, document_id=doc_id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
    b = _make_segment(db, document_id=doc_id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])
    result = registry.invoke(
        db, "segment.match_propose", {"from_segment_id": a.id, "to_segment_id": b.id}, _sys_ctx(db),
    )
    return result.result["match_id"], a, b


def _build_match_accept(db, doc_id):
    match_id, _a, _b = _propose_match(db, doc_id)
    return "POST", f"/api/segments/matches/{match_id}/accept", {}


def _build_match_reject(db, doc_id):
    match_id, _a, _b = _propose_match(db, doc_id)
    return "POST", f"/api/segments/matches/{match_id}/reject", {}


def _build_merge(db, doc_id):
    pass_row = _make_pass(db, doc_id)
    a = _make_segment(db, document_id=doc_id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
    b = _make_segment(db, document_id=doc_id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])
    return "POST", "/api/segments/merge", {
        "segment_ids": [a.id, b.id], "keep_id": b.id,
        # #4957 follow-up 1: now a required field -- irrelevant to what
        # this test checks (authz denial runs before the action's own
        # compare-and-set), but its ABSENCE would 422 before ever
        # reaching the authz check this test exists to exercise.
        "expected_versions": {a.id: a.version, b.id: b.version},
    }


def _build_split(db, doc_id):
    pass_row = _make_pass(db, doc_id)
    seg = _make_segment(db, document_id=doc_id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.2, 0.2])
    return "POST", "/api/segments/split", {
        "segment_id": seg.id, "expected_version": seg.version,
        "parts": [
            {"anchor": {"document_id": doc_id, "rect": [0.0, 0.0, 0.1, 0.1]}},
            {"anchor": {"document_id": doc_id, "rect": [0.1, 0.1, 0.1, 0.1]}},
        ],
    }


def _build_carry(db, doc_id):
    match_id, a, b = _propose_match(db, doc_id)
    registry.invoke(db, "segment.match_accept", {"match_id": match_id}, _sys_ctx(db))
    reading = ContentRepresentation(
        document_id=doc_id, kind=ContentRepresentationKind.transcription,
        content="x", source_anchor=a.anchor,
    )
    db.save(reading)
    return "POST", "/api/segments/carry", {
        "match_id": match_id, "kinds": ["reading"],
        "expected_versions": {a.id: a.version, b.id: b.version},
    }


def _build_update(db, doc_id):
    pass_row = _make_pass(db, doc_id)
    seg = _make_segment(db, document_id=doc_id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
    return "PUT", f"/api/segments/{seg.id}", {
        "segment_id": seg.id, "expected_version": 1,
        "anchor": {"document_id": doc_id, "rect": [0.2, 0.2, 0.1, 0.1]},
    }


def _build_delete(db, doc_id):
    pass_row = _make_pass(db, doc_id)
    seg = _make_segment(db, document_id=doc_id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
    return "POST", "/api/segments/delete", {
        "segment_ids": [seg.id], "expected_versions": {seg.id: 1},
    }


def _build_undelete(db, doc_id):
    pass_row = _make_pass(db, doc_id)
    seg = _make_segment(db, document_id=doc_id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
    registry.invoke(
        db, "segment.delete",
        {"segment_ids": [seg.id], "expected_versions": {seg.id: 1}}, _sys_ctx(db),
    )
    return "POST", "/api/segments/undelete", {"segment_ids": [seg.id]}


def _build_restore_version(db, doc_id):
    pass_row = _make_pass(db, doc_id)
    seg = _make_segment(db, document_id=doc_id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
    registry.invoke(
        db, "segment.update",
        {"segment_id": seg.id, "expected_version": 1,
         "anchor": {"document_id": doc_id, "rect": [0.2, 0.2, 0.1, 0.1]}}, _sys_ctx(db),
    )
    return "POST", f"/api/segments/{seg.id}/restore-version", {"version": 1, "expected_version": 2}


#: (method, router path) -> builder. The KEY is what the router actually
#: declares, so `test_every_write_route_is_covered` can prove this table
#: is exhaustive; the builder does whatever setup that route needs.
_WRITE_ROUTE_CHECKS: dict[tuple[str, str], object] = {
    ("POST", "/segments/passes"): _build_pass_create,
    ("DELETE", "/segments/passes/{pass_id}"): _build_pass_delete,
    ("POST", "/segments"): _build_segment_create,
    ("POST", "/segments/bulk"): _build_segment_bulk,
    ("POST", "/segments/matches"): _build_match_propose,
    ("POST", "/segments/matches/{match_id}/accept"): _build_match_accept,
    ("POST", "/segments/matches/{match_id}/reject"): _build_match_reject,
    ("POST", "/segments/merge"): _build_merge,
    ("POST", "/segments/split"): _build_split,
    ("POST", "/segments/carry"): _build_carry,
    ("PUT", "/segments/{segment_id}"): _build_update,
    ("POST", "/segments/delete"): _build_delete,
    ("POST", "/segments/undelete"): _build_undelete,
    ("POST", "/segments/{segment_id}/restore-version"): _build_restore_version,
}

def _build_read_by_segment_id(db, doc_id):
    pass_row = _make_pass(db, doc_id)
    seg = _make_segment(db, document_id=doc_id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
    return "GET", f"/api/segments/{seg.id}", None


def _build_read_reference(db, doc_id):
    pass_row = _make_pass(db, doc_id)
    seg = _make_segment(db, document_id=doc_id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
    return "GET", f"/api/segments/{seg.id}/reference", None


def _build_read_versions(db, doc_id):
    pass_row = _make_pass(db, doc_id)
    seg = _make_segment(db, document_id=doc_id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
    return "GET", f"/api/segments/{seg.id}/versions", None


#: F2 (review, 2026-09-20): these three reads were previously listed as
#: "not authz-relevant" -- wrong. `target_id_from_request` picks up
#: `segment_id` from the URL PATH for every one of these, which is
#: EXACTLY the id `_target_ancestor_ids` now resolves to its document, so
#: a deny on the document (or a folder above it) must reach them too.
_READ_ROUTE_CHECKS: dict[tuple[str, str], object] = {
    ("GET", "/segments/{segment_id}"): _build_read_by_segment_id,
    ("GET", "/segments/{segment_id}/reference"): _build_read_reference,
    ("GET", "/segments/{segment_id}/versions"): _build_read_versions,
}

#: Read-only routes on the same router with no per-target id to check
#: (the whole-document seam takes a doc_id, already covered by
#: `TestDeniedViewer` in `test_segments_route.py`) -- listed here only so
#: the coverage test can tell "not a write route, nothing more to check"
#: from "forgotten".
_READ_ONLY_ROUTES = {
    ("GET", "/segments/document/{doc_id}"),
}


def test_every_write_route_is_covered():
    """Fails closed: a write route added to the segments router that is
    not listed in `_WRITE_ROUTE_CHECKS` (and not explicitly read-only or
    already covered as a per-target read) fails HERE, by name -- it can
    never ship with its multi-user access silently unchecked."""
    actual_routes = {
        (method, route.path)
        for route in segments_route_module.router.routes
        for method in route.methods
    }
    covered = set(_WRITE_ROUTE_CHECKS.keys()) | set(_READ_ROUTE_CHECKS.keys()) | _READ_ONLY_ROUTES
    missing = actual_routes - covered
    assert not missing, f"route(s) not listed in _WRITE_ROUTE_CHECKS or _READ_ONLY_ROUTES: {sorted(missing)}"
    stale = covered - actual_routes
    assert not stale, f"a listed route no longer exists on the router: {sorted(stale)}"


@pytest.mark.parametrize(
    "route_key,build_request",
    list(_WRITE_ROUTE_CHECKS.items()),
    ids=[f"{m}-{p}" for m, p in _WRITE_ROUTE_CHECKS],
)
class TestEditorDeniedADocumentIsRefusedOnEverySegmentWriteRoute:
    """(1): an editor DENIED a document is refused on EVERY write route
    for that document's segments/passes/matches; the SAME editor SUCCEEDS
    (is not blocked by authz) on a DIFFERENT document -- the positive
    control that proves the refusal is document-scoped, not a global
    lockout of the editor."""

    def test_denied_on_its_own_document_allowed_on_another(
        self, multiuser_client, app_db, users, db, route_key, build_request,
    ):
        client, login, library_path = multiuser_client
        _grant_role(app_db, users.editor, library_path, "editor")

        denied_doc = _make_doc(db, "denied.jpg")
        allowed_doc = _make_doc(db, "allowed.jpg")
        _override(app_db, users.editor, library_path, denied_doc.id, "deny")

        method, url, json_body = build_request(db, denied_doc.id)
        response = client.request(method, url, json=json_body, headers=login("editor"))
        assert response.status_code == 403, (route_key, response.text)

        method2, url2, json_body2 = build_request(db, allowed_doc.id)
        response2 = client.request(method2, url2, json=json_body2, headers=login("editor"))
        assert response2.status_code != 403, (route_key, response2.text)


def test_deny_on_a_folder_above_the_document_reaches_segment_writes(multiuser_client, app_db, users, db):
    """(2): a deny placed on a FOLDER above the document reaches its
    segments -- checked on one representative write route (`segment.create`);
    the ancestor-walk mechanics for every segment-domain KIND are already
    covered exhaustively in `test_authz_ancestor_adversarial.py`."""
    client, login, library_path = multiuser_client
    _grant_role(app_db, users.editor, library_path, "editor")

    folder = Document(name="Denied Folder", doc_type=DocType.folder)
    db.save(folder)
    doc = Document(
        name="doc-in-folder.jpg", doc_type=DocType.file, file_type=None,
        path="/doc-in-folder.jpg", status=Status.completed, parent_id=folder.id,
    )
    db.save(doc)
    _override(app_db, users.editor, library_path, folder.id, "deny")

    method, url, json_body = _build_segment_create(db, doc.id)
    response = client.request(method, url, json=json_body, headers=login("editor"))
    assert response.status_code == 403, response.text


def test_a_grant_on_the_document_overrides_a_folder_deny_for_segment_writes(
    multiuser_client, app_db, users, db,
):
    """(3): a grant on the document overrides a deny on the folder above
    it -- reaching a segment write, not just the document itself."""
    client, login, library_path = multiuser_client
    _grant_role(app_db, users.editor, library_path, "editor")

    folder = Document(name="Denied Folder", doc_type=DocType.folder)
    db.save(folder)
    doc = Document(
        name="granted-doc.jpg", doc_type=DocType.file, file_type=None,
        path="/granted-doc.jpg", status=Status.completed, parent_id=folder.id,
    )
    db.save(doc)
    _override(app_db, users.editor, library_path, folder.id, "deny")
    _override(app_db, users.editor, library_path, doc.id, "grant")

    method, url, json_body = _build_segment_create(db, doc.id)
    response = client.request(method, url, json=json_body, headers=login("editor"))
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "route_key,build_request",
    list(_READ_ROUTE_CHECKS.items()),
    ids=[f"{m}-{p}" for m, p in _READ_ROUTE_CHECKS],
)
class TestViewerDeniedTheDocumentIsRefusedOnEverySegmentIdReadRoute:
    """F2 (review, 2026-09-20): a viewer denied a document must be refused
    on every read route that names a segment id in its URL PATH -- not
    seen working before this, since these three were wrongly listed as
    "not authz-relevant". Positive control: the SAME viewer, on an
    ALLOWED document, gets 200."""

    def test_denied_on_its_own_document_allowed_on_another(
        self, multiuser_client, app_db, users, db, route_key, build_request,
    ):
        client, login, library_path = multiuser_client
        viewer = app_db.create_user(
            username="reader", display_name="Reader",
            password_hash=accounts.hash_password("password"),
        )
        _grant_role(app_db, viewer, library_path, "viewer")

        denied_doc = _make_doc(db, "denied-read.jpg")
        allowed_doc = _make_doc(db, "allowed-read.jpg")
        _override(app_db, viewer, library_path, denied_doc.id, "deny")

        method, url, _ = build_request(db, denied_doc.id)
        response = client.request(method, url, headers=login("reader"))
        assert response.status_code == 403, (route_key, response.text)

        method2, url2, _ = build_request(db, allowed_doc.id)
        response2 = client.request(method2, url2, headers=login("reader"))
        assert response2.status_code == 200, (route_key, response2.text)


class TestArtifactByIdReadReachesTheDocumentsDeny:
    """(4): `GET /api/artifacts/{artifact_id}` and a document's artifact
    list must both honour a deny on the document, by the artifact's OWN
    id -- the seam's `GET /segments/document/{doc_id}` was already
    correct (it takes a doc_id); this is the OTHER read path the
    maintainer's question named."""

    def _make_artifact(self, db, doc_id):
        from fichero_server.models import Artifact

        artifact = Artifact(document_id=doc_id, artifact_type="regions", content="x")
        db.save(artifact)
        return artifact

    def test_viewer_denied_the_document_is_refused_on_get_artifact_by_id(
        self, multiuser_client, app_db, users, db,
    ):
        client, login, library_path = multiuser_client
        viewer = app_db.create_user(
            username="viewer", display_name="Viewer",
            password_hash=accounts.hash_password("password"),
        )
        _grant_role(app_db, viewer, library_path, "viewer")

        denied_doc = _make_doc(db, "denied-artifact.jpg")
        artifact = self._make_artifact(db, denied_doc.id)
        _override(app_db, viewer, library_path, denied_doc.id, "deny")

        r = client.get(f"/api/artifacts/{artifact.id}", headers=login("viewer"))
        assert r.status_code == 403, r.text

        r2 = client.get(f"/api/artifacts/document/{denied_doc.id}", headers=login("viewer"))
        assert r2.status_code == 403, r2.text

    def test_viewer_allowed_on_another_document_gets_200(self, multiuser_client, app_db, users, db):
        client, login, library_path = multiuser_client
        viewer = app_db.create_user(
            username="viewer2", display_name="Viewer2",
            password_hash=accounts.hash_password("password"),
        )
        _grant_role(app_db, viewer, library_path, "viewer")

        allowed_doc = _make_doc(db, "allowed-artifact.jpg")
        artifact = self._make_artifact(db, allowed_doc.id)

        r = client.get(f"/api/artifacts/{artifact.id}", headers=login("viewer2"))
        assert r.status_code == 200, r.text


class TestFailsClosedThroughTheRoute:
    """(5): a lookup error inside authz refuses the REQUEST, not just the
    unit-level `_target_ancestor_ids` call (mutation-proved below)."""

    def test_a_broken_resolver_refuses_an_editors_write(self, multiuser_client, app_db, users, db, monkeypatch):
        client, login, library_path = multiuser_client
        _grant_role(app_db, users.editor, library_path, "editor")
        doc = _make_doc(db, "would-be-allowed.jpg")
        # Ruling 1's cost short-circuit skips resolution entirely when this
        # user has NO overrides -- an override must exist (any target) for
        # the broken resolver to matter here.
        _override(app_db, users.editor, library_path, "some-other-document", "deny")

        def _boom(*_a, **_k):
            raise RuntimeError("simulated authz resolution failure")

        # Patched INSIDE `_target_ancestor_ids`'s own try/except (not the
        # function itself), so the real fail-closed conversion to
        # `AuthzResolutionError` actually runs -- `segment.create`'s
        # `pass_id` target is not itself a Document, so this fires for it.
        monkeypatch.setattr(authz, "_resolve_owning_document_id", _boom)

        method, url, json_body = _build_segment_create(db, doc.id)
        response = client.request(method, url, json=json_body, headers=login("editor"))
        assert response.status_code == 403, response.text


class TestMultiuserOffAndLoopbackOwnerUnaffected:
    """(6): with multi-user OFF, and for the loopback owner, nothing about
    this fix changes ordinary single-user behaviour."""

    def test_ordinary_client_segment_create_unaffected_by_the_resolver_change(self, client, db):
        doc = _make_doc(db, "single-user.jpg")
        r = client.post("/api/segments/passes", json={"document_id": doc.id, "name": "p"})
        assert r.status_code == 200, r.text
        r2 = client.post("/api/segments", json={
            "document_id": doc.id, "pass_id": r.json()["id"], "kind": "word",
            "anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]},
        })
        assert r2.status_code == 200, r2.text


class TestTheHandlerIsGeneralNotSegmentsSpecific:
    """Ruling 2 (2026-09-20): the new `authz.AuthorizationError` handler in
    `api/main.py` sits at the ASGI boundary, not inside `segments.py` or
    `ActionRegistry`, so it must catch a deny on ANY audited write route
    whose target id lives only in the JSON body -- proven here on a
    NON-segment domain (`claim.merge`) -- and must NOT catch an unrelated
    `PermissionError` that has nothing to do with authz."""

    def test_a_non_segment_route_with_a_body_only_id_gets_403_not_500(
        self, multiuser_client, app_db, users, db,
    ):
        from fichero_server.models import KnowledgeClaim

        client, login, library_path = multiuser_client
        _grant_role(app_db, users.editor, library_path, "editor")

        claim_a = KnowledgeClaim(text="Claim A")
        claim_b = KnowledgeClaim(text="Claim B")
        db.save(claim_a)
        db.save(claim_b)
        # `claim.merge`'s ids never appear in the URL -- only in the JSON
        # body -- so the library-path DEPENDENCY's own pre-check (which
        # only sees path/query ids) cannot catch this; only the NEW
        # handler, catching what `ActionRegistry.invoke` itself raises, can.
        _override(app_db, users.editor, library_path, claim_a.id, "deny")

        r = client.post(
            "/api/kg/claims/merge",
            json={"surviving_claim_id": claim_a.id, "absorbed_claim_ids": [claim_b.id]},
            headers=login("editor"),
        )
        assert r.status_code == 403, r.text
        assert r.json().get("code") == "library_access_denied"

        # Positive control: no override at all -- the SAME shape of
        # request succeeds.
        claim_c = KnowledgeClaim(text="Claim C")
        claim_d = KnowledgeClaim(text="Claim D")
        db.save(claim_c)
        db.save(claim_d)
        r2 = client.post(
            "/api/kg/claims/merge",
            json={"surviving_claim_id": claim_c.id, "absorbed_claim_ids": [claim_d.id]},
            headers=login("editor"),
        )
        assert r2.status_code != 403, r2.text

    def test_an_unrelated_permission_error_is_still_a_500(
        self, multiuser_client, app_db, users, db, monkeypatch,
    ):
        """The handler is registered for `authz.AuthorizationError`
        SPECIFICALLY, not the bare `PermissionError` it subclasses -- some
        other, unrelated `PermissionError` raised inside a route must not
        be swallowed into a misleading 403."""
        client, login, library_path = multiuser_client
        _grant_role(app_db, users.editor, library_path, "editor")
        doc = _make_doc(db, "doc.jpg")

        def _boom(*_a, **_k):
            raise PermissionError("unrelated OS-level permission problem")

        monkeypatch.setattr(authz, "assert_can_write", _boom)

        # `TestClient` re-raises an unhandled exception in-process (rather
        # than turning it into a response) precisely BECAUSE nothing
        # caught it -- exactly the proof needed here: the NEW handler is
        # registered for `authz.AuthorizationError` only, so this bare
        # `PermissionError` reaches neither it nor anything else, and a
        # real ASGI server would answer 500, not 403.
        method, url, json_body = _build_segment_create(db, doc.id)
        with pytest.raises(PermissionError, match="unrelated OS-level permission problem"):
            client.request(method, url, json=json_body, headers=login("editor"))


class TestHandlerReportsTheRealRequiredKindPerRaiseSite:
    """F4 (review, 2026-09-20): the handler used to hard-code
    `required="write"`, but `authz.AuthorizationError` is also raised for
    "read access denied", "owner access required" and "cannot revoke your
    own library role" -- each now carries its own `required` on the
    exception (set at the raise site, never hard-coded downstream, never
    parsed from the message). `ActionRegistry.invoke`'s own per-target
    check only ever calls `assert_can_write`, so each OTHER kind is
    exercised here by having that SAME call site raise the shape a real
    caller elsewhere in the codebase would -- proving the HANDLER reads
    `exc.required` correctly for every kind, over a real HTTP request
    through the real registered handler, not a hard-coded assumption."""

    @pytest.mark.parametrize("message,required", [
        ("write access denied", "write"),
        ("read access denied", "read"),
        ("owner access required", "owner"),
        ("cannot revoke your own library role", "owner"),
    ])
    def test_the_reported_required_matches_the_raise_site(
        self, multiuser_client, app_db, users, db, monkeypatch, message, required,
    ):
        client, login, library_path = multiuser_client
        _grant_role(app_db, users.editor, library_path, "editor")
        doc = _make_doc(db, "doc.jpg")

        def _boom(_user, _library, target_id=None):
            # `segment.create`'s route id is BODY-only, so the library-path
            # DEPENDENCY's own pre-check calls this with `target_id=None`
            # and must be let through (it has its OWN, already-correct-for-
            # "write" catch, wrapped into `LibraryAccessDeniedError` before
            # `ActionRegistry.invoke` ever runs) -- only the REGISTRY's own
            # per-target call (a real id) should raise here, so what reaches
            # the NEW handler is the shape a real "read"/"owner" raise site
            # elsewhere in the codebase would produce.
            if target_id is None:
                return
            raise authz.AuthorizationError(message, required=required)

        monkeypatch.setattr(authz, "assert_can_write", _boom)

        method, url, json_body = _build_segment_create(db, doc.id)
        response = client.request(method, url, json=json_body, headers=login("editor"))
        assert response.status_code == 403, response.text
        body = response.json()
        assert body["required"] == required
        assert body["detail"] == message


class TestArtifactAndMatchCrossDocumentRefusal:
    """#4958: `segment.pass_create` never checked that `source_artifact_id`
    belonged to `document_id` (or a descendant page), and silently
    accepted a nonexistent one; `segment.match_propose` never checked its
    two segments shared a document. Slice 6 fills a converted pass's text
    from its source block, so either gap would show one document's words
    on another's page. Refused by the ACTION ITSELF, not by authz -- an
    editor who CAN write to document A is still refused from making A's
    pass name document B's artifact, because this is the segment's own
    document-scope rule, not a permission check."""

    def test_pass_create_refuses_an_artifact_from_a_different_document(self, db):
        doc_a = _make_doc(db, "a.jpg")
        doc_b = _make_doc(db, "b.jpg")
        artifact_b = Artifact(document_id=doc_b.id, artifact_type="regions")
        db.save(artifact_b)

        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "segment.pass_create",
                {"document_id": doc_a.id, "name": "p", "source_artifact_id": artifact_b.id},
                _sys_ctx(db),
            )
        assert exc.value.status_code == 409
        assert db.query(SegmentPass, document_id=doc_a.id) == []

    def test_pass_create_refuses_a_nonexistent_artifact(self, db):
        doc = _make_doc(db, "a.jpg")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "segment.pass_create",
                {"document_id": doc.id, "name": "p", "source_artifact_id": "no-such-artifact"},
                _sys_ctx(db),
            )
        assert exc.value.status_code == 404
        assert db.query(SegmentPass, document_id=doc.id) == []

    def test_pass_create_accepts_an_artifact_from_a_descendant_page(self, db):
        """Same scope `GET /api/artifacts/document/{doc_id}?include_
        descendants=true` uses: the document itself, a direct child page,
        or its parent -- not a stricter, new rule."""
        parent = _make_doc(db, "parent.pdf")
        page = _make_doc(db, "page1.jpg")
        page.parent_id = parent.id
        db.save(page)
        artifact = Artifact(document_id=page.id, artifact_type="regions")
        db.save(artifact)

        result = registry.invoke(
            db, "segment.pass_create",
            {"document_id": parent.id, "name": "p", "source_artifact_id": artifact.id},
            _sys_ctx(db),
        )
        assert result.ok

    def test_match_propose_refuses_segments_on_different_documents(self, db):
        doc_a = _make_doc(db, "a.jpg")
        doc_b = _make_doc(db, "b.jpg")
        pass_a = _make_pass(db, doc_a.id)
        pass_b = _make_pass(db, doc_b.id)
        seg_a = _make_segment(db, document_id=doc_a.id, pass_id=pass_a.id, rect=[0.1, 0.1, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc_b.id, pass_id=pass_b.id, rect=[0.1, 0.1, 0.1, 0.1])

        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "segment.match_propose",
                {"from_segment_id": seg_a.id, "to_segment_id": seg_b.id}, _sys_ctx(db),
            )
        assert exc.value.status_code == 409
        assert db.all(SegmentMatch) == []

    def test_editor_denied_b_is_blocked_by_authz_before_the_4958_check_even_runs(
        self, multiuser_client, app_db, users, db,
    ):
        """`authz.target_ids_from_params` is a BLANKET extractor -- any
        field ending `_id` (here `source_artifact_id`) becomes a checked
        write target -- so an editor DENIED document B is already refused
        with 403 by the registry's OWN authz gate, before `_action_
        pass_create` (and #4958's new check inside it) ever runs. This is
        the FIRST line of defense; the next test shows why #4958's check
        is still needed as a second one."""
        client, login, library_path = multiuser_client
        _grant_role(app_db, users.editor, library_path, "editor")

        doc_a = _make_doc(db, "a.jpg")
        doc_b = _make_doc(db, "b.jpg")
        _override(app_db, users.editor, library_path, doc_b.id, "deny")
        artifact_b = Artifact(document_id=doc_b.id, artifact_type="regions")
        db.save(artifact_b)

        response = client.post(
            "/api/segments/passes",
            json={"document_id": doc_a.id, "name": "p", "source_artifact_id": artifact_b.id},
            headers=login("editor"),
        )
        assert response.status_code == 403, response.text
        assert db.query(SegmentPass, document_id=doc_a.id) == []

    def test_editor_with_broad_access_to_both_still_cannot_make_as_pass_name_bs_artifact(
        self, multiuser_client, app_db, users, db,
    ):
        """The case authz alone does NOT catch: an editor whose role
        covers every document (no per-document deny anywhere -- the
        common, unrestricted "editor" grant) can write to A and, per
        authz, "write" `source_artifact_id`=B's artifact too (the same
        blanket `_id` extraction that blocked the denied case above says
        yes here, since nothing denies B). #4958's own document-scope
        check is what still refuses A's pass from naming B's artifact --
        independent of, and a second line of defense beyond, authz."""
        client, login, library_path = multiuser_client
        _grant_role(app_db, users.editor, library_path, "editor")

        doc_a = _make_doc(db, "a.jpg")
        doc_b = _make_doc(db, "b.jpg")
        artifact_b = Artifact(document_id=doc_b.id, artifact_type="regions")
        db.save(artifact_b)

        response = client.post(
            "/api/segments/passes",
            json={"document_id": doc_a.id, "name": "p", "source_artifact_id": artifact_b.id},
            headers=login("editor"),
        )
        assert response.status_code == 409, response.text
        assert db.query(SegmentPass, document_id=doc_a.id) == []
