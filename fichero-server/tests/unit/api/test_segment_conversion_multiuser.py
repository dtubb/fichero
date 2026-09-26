"""Slice 6 (#4924) -- who may convert a page, asserted ON ROWS.

A 403 is not the assertion that matters. The question is whether the
conversion RAN before the refusal: a check that happens after the write is
a check that protects nothing, and its test would still be green. So every
case here asserts zero segment rows, zero passes, no marker, and an
artifact byte-equal to what it was -- and only then the status.

`ActionRegistry.invoke` is the real path: it calls `authz.assert_can_write`
for every id `authz.target_ids_from_params` finds in the params, BEFORE
`execute` and before the transaction opens. The action's own HTTP route
arrives with the edit half (step 5, #4924); testing the registry is testing
the place the check actually lives.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType, Segment, SegmentPass, Status
from fichero_server.security import accounts, authz

pytestmark = pytest.mark.source_model


@pytest.fixture
def multiuser(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    yield


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
    viewer = app_db.create_user(
        username="viewer", display_name="Viewer",
        password_hash=accounts.hash_password("password"),
    )
    return {"owner": owner, "editor": editor, "viewer": viewer}


def _grant(app_db, user, library_path: str, role: str) -> None:
    app_db.set_library_role(
        user_id=user.id, library_path=authz.normalize_library_path(library_path), role=role,
    )


def _deny(app_db, user, library_path: str, target_id: str) -> None:
    app_db.set_library_acl_override(
        user_id=user.id, library_path=authz.normalize_library_path(library_path),
        target_id=target_id, effect="deny",
    )


def _make_doc(db, name: str, parent_id: str | None = None, doc_type=DocType.file) -> Document:
    doc = Document(
        name=name, doc_type=doc_type,
        file_type=FileType.image if doc_type is DocType.file else None,
        path=f"/{name}", status=Status.completed, parent_id=parent_id,
    )
    db.save(doc)
    return doc


def _artifact(db, doc) -> Artifact:
    artifact = Artifact(
        document_id=doc.id, artifact_type="transcription", provider="qwen",
        ocr_geometry=OCRGeometryResult(
            provider="qwen", text="uno dos",
            boxes=[
                OCRGeometryBox(text="uno", bbox=[0.1, 0.1, 0.2, 0.05]),
                OCRGeometryBox(text="dos", bbox=[0.1, 0.3, 0.2, 0.05]),
            ],
        ),
    )
    db.save(artifact)
    return artifact


def _ctx(db, user) -> ActionContext:
    return ActionContext(actor=user.id, library_path=str(db.path.parent))


#: A real edit, so `artifact_id` rides in the params beside `document_id`.
#: That is the whole point here: `authz.target_ids_from_params` checks them
#: as two INDEPENDENT targets, and a deny on either must stop the write.
A_TRIVIAL_EDIT = {"op": "move", "indices": [0], "bbox": [0.1, 0.1, 0.2, 0.05]}


def _convert(db, user, doc, artifact):
    return registry.invoke(
        db, "segment.convert_and_edit",
        {"document_id": doc.id, "artifact_id": artifact.id, "edit": A_TRIVIAL_EDIT},
        _ctx(db, user),
    )


def _assert_nothing_happened(db, doc, artifact, before: dict) -> None:
    """The assertion that a 403 alone cannot make: the conversion must not
    have run BEFORE the refusal."""
    assert db.query(Segment, document_id=doc.id) == [], "segment rows were written anyway"
    assert db.query(SegmentPass, document_id=doc.id) == [], "a pass was written anyway"
    reread = db.get(Artifact, artifact.id)
    assert reread.geometry_superseded_by_pass_id is None, "the artifact was marked anyway"
    assert reread.model_dump(mode="json") == before, "the artifact row changed"


class TestAViewerCannotConvert:
    def test_a_viewers_first_edit_is_refused_and_writes_nothing(
        self, db, app_db, users, multiuser
    ):
        doc = _make_doc(db, "page.jpg")
        artifact = _artifact(db, doc)
        before = db.get(Artifact, artifact.id).model_dump(mode="json")
        _grant(app_db, users["viewer"], str(db.path.parent), "viewer")

        with pytest.raises(PermissionError):
            _convert(db, users["viewer"], doc, artifact)
        _assert_nothing_happened(db, doc, artifact, before)


class TestAnEditorDeniedThisDocument:
    def test_it_is_refused_and_writes_nothing(self, db, app_db, users, multiuser):
        doc = _make_doc(db, "page.jpg")
        artifact = _artifact(db, doc)
        before = db.get(Artifact, artifact.id).model_dump(mode="json")
        _grant(app_db, users["editor"], str(db.path.parent), "editor")
        _deny(app_db, users["editor"], str(db.path.parent), doc.id)

        with pytest.raises(PermissionError):
            _convert(db, users["editor"], doc, artifact)
        _assert_nothing_happened(db, doc, artifact, before)

    def test_the_same_editor_still_converts_a_document_they_may_write(
        self, db, app_db, users, multiuser
    ):
        """The positive control. Without it, a rule that refused EVERY
        editor would pass the test above."""
        denied = _make_doc(db, "denied.jpg")
        allowed = _make_doc(db, "allowed.jpg")
        _artifact(db, denied)
        artifact = _artifact(db, allowed)
        _grant(app_db, users["editor"], str(db.path.parent), "editor")
        _deny(app_db, users["editor"], str(db.path.parent), denied.id)

        result = _convert(db, users["editor"], allowed, artifact)
        assert result.result["segment_count"] == 2
        assert db.get(Artifact, artifact.id).geometry_superseded_by_pass_id is not None

    def test_a_deny_on_a_folder_above_reaches_the_page(self, db, app_db, users, multiuser):
        """#4917: a restriction on a folder reaches the documents under it,
        and through them their artifacts."""
        folder = _make_doc(db, "1948", doc_type=DocType.folder)
        page = _make_doc(db, "page.jpg", parent_id=folder.id)
        artifact = _artifact(db, page)
        before = db.get(Artifact, artifact.id).model_dump(mode="json")
        _grant(app_db, users["editor"], str(db.path.parent), "editor")
        _deny(app_db, users["editor"], str(db.path.parent), folder.id)

        with pytest.raises(PermissionError):
            _convert(db, users["editor"], page, artifact)
        _assert_nothing_happened(db, page, artifact, before)


class TestTheWholePageBelongsToOnePerson:
    def test_converting_one_page_converts_every_result_on_it(
        self, db, app_db, users, multiuser
    ):
        """All the results belong to that one document, so the one check on
        the document covers every artifact the conversion touches. Pinned
        so nobody later 'optimises' the loop to skip a check that was never
        needed per artifact."""
        doc = _make_doc(db, "page.jpg")
        first = _artifact(db, doc)
        second = _artifact(db, doc)
        _grant(app_db, users["editor"], str(db.path.parent), "editor")

        result = _convert(db, users["editor"], doc, first)
        assert set(result.result["artifact_ids"]) == {first.id, second.id}
        assert result.result["segment_count"] == 4


class TestAnOwnerIsUnaffected:
    def test_an_owner_converts(self, db, app_db, users, multiuser):
        doc = _make_doc(db, "page.jpg")
        artifact = _artifact(db, doc)
        _grant(app_db, users["owner"], str(db.path.parent), "owner")
        result = _convert(db, users["owner"], doc, artifact)
        assert result.result["segment_count"] == 2
