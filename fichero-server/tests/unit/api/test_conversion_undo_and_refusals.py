"""Slice 6 (#4924) -- the four FIX FIRSTs from the author's review.

1. Undoing an OLD artifact action after conversion must not clear the
   marker and fork the page into two stores.
2. A dangling marker must be a typed 409 everywhere, not a 500 on the
   document view.
3. The audit chain carries counts, never the unbounded match list.
4. Every typed refusal reaches a caller as its own status, not a 500.
"""

from __future__ import annotations

import json

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.core.timeutil import utc_now
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import ActionAudit, Artifact, DocType, Document, FileType, Status
from fichero_server.models.segments import Segment, SegmentPass, converted_pass_id

pytestmark = pytest.mark.source_model


#: Where a test needs the WORKING-pass form -- `artifact_id` and `edit`
#: together -- without the edit being what is under test.
A_TRIVIAL_EDIT = {"op": "move", "indices": [0], "bbox": [0.1, 0.1, 0.2, 0.05]}


def _ctx() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _make_doc(db, name: str = "page.jpg") -> Document:
    doc = Document(
        name=name, doc_type=DocType.file, file_type=FileType.image,
        path=f"/path/{name}", status=Status.completed,
    )
    db.save(doc)
    return doc


def _artifact(db, doc, count: int = 3) -> Artifact:
    artifact = Artifact(
        document_id=doc.id, artifact_type="transcription", provider="qwen",
        ocr_geometry=OCRGeometryResult(
            provider="qwen", text=" ".join(f"w{i}" for i in range(count)),
            boxes=[
                OCRGeometryBox(text=f"w{i}", bbox=[0.1, 0.1 + i * 0.1, 0.2, 0.05])
                for i in range(count)
            ],
        ),
    )
    db.save(artifact)
    return artifact


def _seam(client, doc_id: str):
    r = client.get(f"/api/segments/document/{doc_id}")
    assert r.status_code == 200, r.text
    return r.json()


class TestUndoingAnOldArtifactActionAfterConversion:
    """FIX FIRST 1, traced exactly as the review traced it."""

    def test_undoing_a_pre_conversion_regions_edit_is_refused(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)

        edit = registry.invoke(
            db, "artifact.regions_edit",
            {"artifact_id": artifact.id, "edit": {"op": "move", "indices": [1],
                                                  "bbox": [0.5, 0.5, 0.1, 0.1]}},
            _ctx(),
        )
        registry.invoke(
            db, "segment.convert_and_edit",
            {"document_id": doc.id}, _ctx(),
        )
        audit = db.get(ActionAudit, edit.audit_id)
        name, params = registry.get("artifact.regions_edit").invert(
            audit.before, audit.after, _ctx()
        )
        assert name == "artifact.restore"

        with pytest.raises(Exception) as caught:
            registry.invoke(db, name, params, _ctx())
        assert type(caught.value).__name__ == "ArtifactGeometryRestoreRefused"

    def test_the_marker_is_still_set_and_each_box_comes_back_once(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        edit = registry.invoke(
            db, "artifact.regions_edit",
            {"artifact_id": artifact.id, "edit": {"op": "move", "indices": [1],
                                                  "bbox": [0.5, 0.5, 0.1, 0.1]}},
            _ctx(),
        )
        registry.invoke(
            db, "segment.convert_and_edit",
            {"document_id": doc.id}, _ctx(),
        )
        audit = db.get(ActionAudit, edit.audit_id)
        name, params = registry.get("artifact.regions_edit").invert(
            audit.before, audit.after, _ctx()
        )
        with pytest.raises(Exception):
            registry.invoke(db, name, params, _ctx())

        reread = db.get(Artifact, artifact.id)
        assert reread.geometry_superseded_by_pass_id == converted_pass_id(artifact.id)
        body = _seam(client, doc.id)
        assert len(body["passes"]) == 1, "the page forked into two stores"
        assert len(body["segments"]) == 3, "every box came back twice"
        assert all(s["provisional"] is False for s in body["segments"])

    def test_a_restore_never_decides_whether_a_page_is_converted(self, db):
        """THE INVARIANT. A dump with no marker cannot un-convert a page,
        because the marker is read from the store, not the payload."""
        from fichero_server.api.routes.document.artifacts import _restore_artifact_impl

        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        payload_before_conversion = db.get(Artifact, artifact.id).model_dump(mode="json")
        assert payload_before_conversion["geometry_superseded_by_pass_id"] is None

        registry.invoke(
            db, "segment.convert_and_edit",
            {"document_id": doc.id}, _ctx(),
        )
        # Same boxes as the kept block, so it is not refused -- and the
        # marker must survive anyway.
        restored = _restore_artifact_impl(db, payload_before_conversion)
        assert restored.geometry_superseded_by_pass_id == converted_pass_id(artifact.id)
        assert db.get(Artifact, artifact.id).geometry_superseded_by_pass_id is not None

    def test_deleting_a_converted_artifact_is_refused(self, db):
        """RULED 2026-09-20. Until readings hang on segments, this result
        holds the WORDS of every segment on the page. Deleting it would
        leave that page readable in outline and blank in substance, and
        nothing would say so."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        registry.invoke(
            db, "segment.convert_and_edit",
            {"document_id": doc.id}, _ctx(),
        )
        with pytest.raises(Exception) as caught:
            registry.invoke(db, "artifact.delete", {"artifact_id": artifact.id}, _ctx())
        assert type(caught.value).__name__ == "ArtifactHoldsTheOnlyWords"
        assert db.get(Artifact, artifact.id) is not None, "nothing may be written"

    def test_the_refusal_says_what_a_person_can_do_instead(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        registry.invoke(
            db, "segment.convert_and_edit",
            {"document_id": doc.id}, _ctx(),
        )
        r = client.delete(f"/api/artifacts/{artifact.id}")
        assert r.status_code == 409, r.text
        assert "words" in r.text and "segments" in r.text

    def test_an_artifact_already_gone_still_reads_honestly_and_restores_marked(
        self, db, client
    ):
        """Older data, an import, or a delete that predates the refusal:
        the rows outlive the artifact. The page must still read -- shapes
        in the right order, no words, no raise -- and a restore must bring
        it back MARKED, not as an unconverted twin of a page that already
        has segments."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        registry.invoke(
            db, "segment.convert_and_edit",
            {"document_id": doc.id}, _ctx(),
        )
        snapshot = db.get(Artifact, artifact.id).model_dump(mode="json")
        db.delete(db.get(Artifact, artifact.id))  # the STATE, not the route
        assert db.get(Artifact, artifact.id) is None

        between = _seam(client, doc.id)
        assert len(between["segments"]) == 3
        assert all(s["text"] is None for s in between["segments"])
        assert len(between["passes"]) == 1

        registry.invoke(db, "artifact.restore", {"payload": snapshot}, _ctx())
        reread = db.get(Artifact, artifact.id)
        assert reread.geometry_superseded_by_pass_id == converted_pass_id(artifact.id)
        after = _seam(client, doc.id)
        assert [s["text"] for s in after["segments"]] == ["w0", "w1", "w2"]

    def test_a_document_restore_replaying_snapshots_keeps_the_marker(self, db):
        """The sibling of the same defect, found by sweeping every whole-row
        artifact writer: `documents.py` replays recorded artifact snapshots
        the same way."""
        from fichero_server.api.routes.document.documents import restore_documents_impl

        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        snapshot = db.get(Artifact, artifact.id).model_dump(mode="json")
        registry.invoke(
            db, "segment.convert_and_edit",
            {"document_id": doc.id}, _ctx(),
        )

        restore_documents_impl(db, doc_ids=[], documents=[], artifacts=[snapshot])
        assert db.get(Artifact, artifact.id).geometry_superseded_by_pass_id is not None


class TestADanglingMarkerIsNeverA500:
    """FIX FIRST 2, the handler half."""

    @staticmethod
    def _dangle(db, doc):
        artifact = _artifact(db, doc)
        registry.invoke(
            db, "segment.convert_and_edit",
            {"document_id": doc.id}, _ctx(),
        )
        pass_row = db.get(SegmentPass, converted_pass_id(artifact.id))
        pass_row.deleted_at = utc_now()
        db.save(pass_row)
        return artifact

    @pytest.mark.parametrize(
        "path",
        [
            "/api/artifacts/{artifact_id}",
            "/api/artifacts/document/{doc_id}",
            "/api/documents/{doc_id}/view",
            "/api/segments/document/{doc_id}",
        ],
    )
    def test_every_route_that_touches_it_answers_409_not_500(self, db, client, path):
        doc = _make_doc(db)
        artifact = self._dangle(db, doc)
        r = client.get(path.format(artifact_id=artifact.id, doc_id=doc.id))
        assert r.status_code == 409, f"{path} -> {r.status_code}: {r.text[:200]}"

    def test_the_answer_names_the_page_that_needs_repair(self, db, client):
        doc = _make_doc(db)
        artifact = self._dangle(db, doc)
        r = client.get(f"/api/artifacts/{artifact.id}")
        assert artifact.id in r.text and converted_pass_id(artifact.id) in r.text

    def test_the_stale_block_is_never_in_the_answer(self, db, client):
        doc = _make_doc(db)
        self._dangle(db, doc)
        r = client.get(f"/api/documents/{doc.id}/view")
        assert "w0" not in r.text


class TestTheAuditChainStaysSmall:
    """FIX FIRST 3."""

    def test_the_match_list_is_in_the_result_and_the_count_in_the_chain(self, db):
        from fichero_server.models import ContentRepresentation, ContentRepresentationKind
        from fichero_server.models.anchors import SourceAnchor

        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        rect = list(artifact.ocr_geometry.boxes[0].bbox)
        for i in range(60):
            db.save(ContentRepresentation(
                document_id=doc.id, kind=ContentRepresentationKind.transcription,
                content=f"reading {i}",
                source_anchor=SourceAnchor(document_id=doc.id, rect=rect),
            ))

        result = registry.invoke(
            db, "segment.convert_and_edit",
            {"document_id": doc.id}, _ctx(),
        )
        assert len(result.result["not_repointed"]) == 60, "the caller gets the list"
        assert result.result["not_repointed_count"] == 60

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.after["not_repointed_count"] == 60, "the chain gets the count"
        assert "not_repointed" not in audit.after, "the chain must not grow with the page"
        payload = json.dumps(audit.after)
        assert len(payload) < 10_000, f"{len(payload)} bytes"

    def test_the_payload_assertion_means_something_now(self, db):
        """It used to pass only because the page had no anchored records."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        result = registry.invoke(
            db, "segment.convert_and_edit",
            {"document_id": doc.id}, _ctx(),
        )
        assert db.get(ActionAudit, result.audit_id).after["not_repointed_count"] == 0


class TestEveryTypedRefusalReachesItsCaller:
    """FIX FIRST 4. The action is registered, so it is callable TODAY
    through the generic invoke route, which catches only not-found,
    validation and authorization."""

    @pytest.mark.parametrize(
        "build, expected",
        [
            (lambda doc, art: {"document_id": "no-such-document"}, 404),
            (
                lambda doc, art: {
                    "document_id": doc.id,
                    "artifact_id": "no-such-artifact",
                    "edit": A_TRIVIAL_EDIT,
                },
                404,
            ),
            (lambda doc, art: {"document_id": doc.id}, 409),  # nothing to convert
        ],
    )
    def test_the_generic_invoke_route_answers_the_typed_status(
        self, db, client, build, expected
    ):
        doc = _make_doc(db)
        empty = _make_doc(db, "empty.jpg")
        params = build(empty if expected == 409 else doc, None)
        r = client.post(
            "/api/actions/invoke",
            json={"name": "segment.convert_and_edit", "params": params},
        )
        assert r.status_code == expected, f"{r.status_code}: {r.text[:200]}"

    def test_already_converted_is_a_409_through_the_route(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        body = {"name": "segment.convert_and_edit",
                "params": {"document_id": doc.id}}
        assert client.post("/api/actions/invoke", json=body).status_code == 200
        r = client.post("/api/actions/invoke", json=body)
        assert r.status_code == 409, f"{r.status_code}: {r.text[:200]}"

    def test_an_artifact_from_another_document_is_a_422_through_the_route(self, db, client):
        doc_a, doc_b = _make_doc(db, "a.jpg"), _make_doc(db, "b.jpg")
        _artifact(db, doc_a)
        b1 = _artifact(db, doc_b)
        r = client.post(
            "/api/actions/invoke",
            json={"name": "segment.convert_and_edit",
                  "params": {"document_id": doc_a.id, "artifact_id": b1.id,
                             "edit": A_TRIVIAL_EDIT}},
        )
        assert r.status_code == 422, f"{r.status_code}: {r.text[:200]}"

    def test_a_conversion_with_no_edit_has_no_inverse_rather_than_raising(self, db):
        """The history would otherwise list it as undoable and 500 when
        somebody pressed undo."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        result = registry.invoke(
            db, "segment.convert_and_edit",
            {"document_id": doc.id}, _ctx(),
        )
        audit = db.get(ActionAudit, result.audit_id)
        reg = registry.get("segment.convert_and_edit")
        assert reg.invert(audit.before, audit.after, _ctx()) is None
