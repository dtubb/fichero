"""Rights and consent records (slice 14, #4953; `rights-and-access.md`).

What a record says, and what the records above a target ADD UP TO. Enforcement -- who is refused
what (`source.rights.one-check`) -- is a separate question and is not pinned here.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import fichero_server.api.routes.document.rights  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.rights import effective_rights
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.rights import RightsRecord
from fichero_server.models.segments import Segment, SegmentPass
from fichero_server.security import accounts, authz

pytestmark = pytest.mark.source_model

CTX = ActionContext(actor="archivist", library_path=None, is_bootstrap=True)


@pytest.fixture
def tree(db):
    """library > folder > letter (a document) > one segment on it."""
    folder = Document(name="Letters", doc_type=DocType.folder)
    db.save(folder)
    letter = Document(name="letter.jpg", doc_type=DocType.file, file_type=FileType.image,
                      path="/p/letter.jpg", status=Status.completed, parent_id=folder.id)
    db.save(letter)
    pass_row = SegmentPass(document_id=letter.id, name="p", provenance_kind=ProvenanceKind.human)
    db.save(pass_row)
    import fichero_server.api.routes.document.segments  # noqa: F401  (registers segment.create)

    made = registry.invoke(db, "segment.create", {
        "document_id": letter.id, "pass_id": pass_row.id, "kind": "line",
        "anchor": {"document_id": letter.id, "rect": [0.1, 0.1, 0.2, 0.05]}}, CTX).result
    segment = db.get(Segment, made["segment_ids"][0])
    return folder, letter, segment


def _set(db, **params):
    return registry.invoke(db, "rights.set", params, CTX).result["record_id"]


class TestARecordSaysWhatItSays:
    def test_a_record_hangs_on_the_library_a_source_or_a_segment_with_open_labels(self, db, tree):
        """`source.rights.record`."""
        folder, letter, segment = tree
        ids = [
            _set(db, target_kind="library", labels=["TK Attribution"]),
            _set(db, target_kind="document", target_id=letter.id, holders=["The family"],
                 consent={"what": "research use", "by": "the family", "when": "2024-05-01"}),
            _set(db, target_kind="segment", target_id=segment.id, labels=["project: sensitive"]),
        ]
        kinds = [db.get(RightsRecord, i).target_kind for i in ids]
        assert kinds == ["library", "document", "segment"]
        assert db.get(RightsRecord, ids[1]).consent["by"] == "the family"
        assert db.get(RightsRecord, ids[0]).created_by == "archivist", "the maker is the engine's answer"

    def test_a_target_that_does_not_exist_is_refused(self, db, tree):
        with pytest.raises(HTTPException) as refused:
            _set(db, target_kind="segment", target_id="no-such-segment")
        assert refused.value.status_code == 404

    def test_a_restriction_that_names_nobody_is_refused(self, db, tree):
        folder, letter, segment = tree
        with pytest.raises(HTTPException) as refused:
            _set(db, target_kind="document", target_id=letter.id, restricted=True)
        assert refused.value.status_code == 422


class TestItPassesDownAndOnlyTightens:
    """`source.rights.tighten-only`."""

    def test_a_restriction_above_covers_everything_below(self, db, tree):
        folder, letter, segment = tree
        _set(db, target_kind="document", target_id=folder.id, restricted=True, readers=["u-ana", "u-ben"])
        effective = effective_rights(db, "segment", segment.id)
        assert effective.restricted and effective.readers == {"u-ana", "u-ben"}

    def test_a_lower_record_narrows_who_may_see_and_cannot_widen_it(self, db, tree):
        folder, letter, segment = tree
        _set(db, target_kind="document", target_id=folder.id, restricted=True, readers=["u-ana", "u-ben"])
        _set(db, target_kind="segment", target_id=segment.id, restricted=True, readers=["u-ben", "u-cleo"])
        assert effective_rights(db, "segment", segment.id).readers == {"u-ben"}, "cleo was never allowed above"
        assert effective_rights(db, "document", letter.id).readers == {"u-ana", "u-ben"}, "the segment's record stays on it"

    def test_an_unrestricted_record_below_does_not_lift_a_restriction_above(self, db, tree):
        folder, letter, segment = tree
        _set(db, target_kind="document", target_id=letter.id, restricted=True, readers=["u-ana"])
        _set(db, target_kind="segment", target_id=segment.id, restricted=False, labels=["x"])
        assert effective_rights(db, "segment", segment.id).restricted

    def test_model_use_takes_the_strictest_and_a_looser_record_is_refused_out_loud(self, db, tree):
        folder, letter, segment = tree
        _set(db, target_kind="library", model_use="local")
        with pytest.raises(HTTPException) as refused:
            _set(db, target_kind="document", target_id=letter.id, model_use="cloud")
        assert refused.value.status_code == 422 and "only tighten" in refused.value.detail
        _set(db, target_kind="segment", target_id=segment.id, model_use="none")
        assert effective_rights(db, "segment", segment.id).model_use == "none"
        assert effective_rights(db, "document", letter.id).model_use == "local"


class TestWithdrawingAndUndo:
    def test_a_withdrawn_record_stops_applying_and_undo_brings_it_back(self, db, client, tree):
        folder, letter, segment = tree
        record_id = _set(db, target_kind="document", target_id=letter.id, restricted=True, readers=["u-ana"])
        withdrawn = registry.invoke(db, "rights.withdraw", {"record_id": record_id}, CTX)
        assert not effective_rights(db, "segment", segment.id).restricted
        assert client.post(f"/api/actions/audit/{withdrawn.audit_id}/undo").status_code == 200
        assert effective_rights(db, "segment", segment.id).restricted

    def test_the_effective_route_says_what_applies_and_which_records(self, db, client, tree):
        folder, letter, segment = tree
        _set(db, target_kind="library", labels=["BC Provenance"])
        _set(db, target_kind="document", target_id=folder.id, restricted=True, readers=["u-ana"])
        body = client.get("/api/rights/effective", params={"target_kind": "segment", "target_id": segment.id}).json()
        assert body["restricted"] is True and body["readers"] == ["u-ana"]
        assert body["labels"] == ["BC Provenance"]
        assert [r["target_kind"] for r in body["records"]] == ["library", "document"]


class TestWhoActs:
    """`source.rights.who-acts`: owners and editors set records; a viewer is refused -- by the
    existing write check, because a record's target is a write target."""

    def test_a_viewer_cannot_set_a_record_and_an_editor_can(self, db, app_db, tree, monkeypatch):
        folder, letter, segment = tree
        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        library_path = str(db.path.parent)
        for name, role in (("rights-viewer", "viewer"), ("rights-editor", "editor")):
            user = app_db.create_user(username=name, display_name=name, password_hash=accounts.hash_password("password"))
            app_db.set_library_role(user_id=user.id, library_path=authz.normalize_library_path(library_path), role=role)
        params = {"target_kind": "document", "target_id": letter.id, "labels": ["x"]}
        with pytest.raises(authz.AuthorizationError):
            registry.invoke(db, "rights.set", params, ActionContext(actor="rights-viewer", library_path=library_path))
        registry.invoke(db, "rights.set", params, ActionContext(actor="rights-editor", library_path=library_path))
        assert len([r for r in db.all(RightsRecord) if r.target_id == letter.id]) == 1
