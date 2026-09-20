"""Source-model slice 3 — Segment/SegmentPass writes (#4921).

`POST /api/segments/passes`, `DELETE /api/segments/passes/{pass_id}`,
`POST /api/segments`, `POST /api/segments/bulk` — the first writes in the
source model, each one typed, audited action. Each test names the
behaviour id it pins.
"""

from __future__ import annotations

import time

import pytest

from fichero_server.models import (
    ActionAudit,
    Artifact,
    DocType,
    Document,
    FileType,
    Segment,
    SegmentPass,
    Status,
)

pytestmark = pytest.mark.source_model


def _make_doc(db, name: str = "page.jpg") -> Document:
    doc = Document(
        name=name, doc_type=DocType.file, file_type=FileType.image,
        path=f"/path/{name}", status=Status.completed,
    )
    db.save(doc)
    return doc


def _create_pass(client, document_id: str, **kwargs) -> dict:
    r = client.post("/api/segments/passes", json={"document_id": document_id, "name": "test-pass", **kwargs})
    assert r.status_code == 200, r.text
    return r.json()


def _create_segment(client, *, document_id: str, pass_id: str, kind: str = "word", anchor=None, **kwargs) -> dict:
    body = {
        "document_id": document_id,
        "pass_id": pass_id,
        "kind": kind,
        "anchor": anchor or {"document_id": document_id, "rect": [0.1, 0.1, 0.2, 0.1]},
        **kwargs,
    }
    r = client.post("/api/segments", json=body)
    return r


class TestLastingId:
    def test_create_read_back_engine_made_id_client_id_refused(self, client, db):
        """source.segment.lasting-id."""
        doc = _make_doc(db)
        pass_body = _create_pass(client, doc.id)
        assert pass_body["id"]
        assert pass_body["document_id"] == doc.id

        r = _create_segment(client, document_id=doc.id, pass_id=pass_body["id"])
        assert r.status_code == 200, r.text
        segment = r.json()
        assert segment["id"]
        assert segment["provisional"] is False

        stored = db.get(Segment, segment["id"])
        assert stored is not None
        assert stored.id == segment["id"]

        # A client-supplied id is refused -- the params model has no `id`
        # field at all, so `extra="forbid"` rejects it.
        r2 = client.post(
            "/api/segments",
            json={
                "id": "client-chosen-id",
                "document_id": doc.id, "pass_id": pass_body["id"], "kind": "word",
                "anchor": {"document_id": doc.id, "rect": [0.5, 0.5, 0.1, 0.1]},
            },
        )
        assert r2.status_code == 422


class TestBoxIsDerived:
    def test_bbox_columns_match_anchor_for_rect_and_polygon_supplying_them_is_refused(self, client, db):
        """source.segment.box-is-derived."""
        doc = _make_doc(db)
        pass_body = _create_pass(client, doc.id)

        r = _create_segment(
            client, document_id=doc.id, pass_id=pass_body["id"],
            anchor={"document_id": doc.id, "rect": [0.1, 0.2, 0.3, 0.4]},
        )
        assert r.status_code == 200, r.text
        stored = db.get(Segment, r.json()["id"])
        assert (stored.bbox_x, stored.bbox_y, stored.bbox_w, stored.bbox_h) == (0.1, 0.2, 0.3, 0.4)

        polygon = [[0.1, 0.1], [0.4, 0.1], [0.4, 0.3], [0.1, 0.3]]
        r2 = _create_segment(
            client, document_id=doc.id, pass_id=pass_body["id"],
            anchor={"document_id": doc.id, "polygon": polygon},
        )
        assert r2.status_code == 200, r2.text
        stored2 = db.get(Segment, r2.json()["id"])
        assert (stored2.bbox_x, stored2.bbox_y) == (0.1, 0.1)
        assert round(stored2.bbox_w, 6) == 0.3
        assert round(stored2.bbox_h, 6) == 0.2

        # Supplying bbox_* (or tile) is refused: the params model does not
        # declare them, so extra="forbid" rejects the request outright.
        r3 = client.post(
            "/api/segments",
            json={
                "document_id": doc.id, "pass_id": pass_body["id"], "kind": "word",
                "anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]},
                "bbox_x": 0.1, "bbox_y": 0.1, "bbox_w": 0.1, "bbox_h": 0.1,
            },
        )
        assert r3.status_code == 422


class TestOnePrimitiveOpenKinds:
    def test_region_line_word_picture_all_segments_unknown_kind_roundtrips_kind_raw_kept(
        self, client, db,
    ):
        """source.segment.one-primitive, source.segment.open-kinds."""
        doc = _make_doc(db)
        pass_body = _create_pass(client, doc.id)

        for kind in ("region", "line", "word", "picture", "a-projects-own-kind"):
            r = _create_segment(
                client, document_id=doc.id, pass_id=pass_body["id"], kind=kind,
                kind_raw="ModelsOwnLabel",
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["kind"] == kind
            assert body["kind_raw"] == "ModelsOwnLabel"
            stored = db.get(Segment, body["id"])
            assert isinstance(stored, Segment)
            assert stored.kind == kind
            assert stored.kind_raw == "ModelsOwnLabel"


class TestPassesNamedAuthoredNeverOverwrite:
    def test_two_passes_keep_separate_segments_second_touches_no_row_of_first(self, client, db):
        """source.pass.named-authored, source.pass.never-overwrites,
        source.segment.rerun-is-new-pass."""
        doc = _make_doc(db)
        pass_1 = _create_pass(client, doc.id, name="first layout")
        pass_2 = _create_pass(client, doc.id, name="second layout")
        assert pass_1["id"] != pass_2["id"]

        seg_1 = _create_segment(client, document_id=doc.id, pass_id=pass_1["id"]).json()
        before_pass_1_row = db.get(Segment, seg_1["id"]).model_dump(mode="json")
        before_count = len(db.query(Segment, pass_id=pass_1["id"]))

        seg_2 = _create_segment(client, document_id=doc.id, pass_id=pass_2["id"]).json()

        assert db.get(Segment, seg_1["id"]).model_dump(mode="json") == before_pass_1_row
        assert len(db.query(Segment, pass_id=pass_1["id"])) == before_count
        assert len(db.query(Segment, pass_id=pass_2["id"])) == 1
        assert seg_1["id"] != seg_2["id"]


class TestSegmentMakerIsWhoActed:
    """test-audit F14, 2026-09-20 -- LIKELY DEFECT, confirmed then fixed:
    `_action_segment_create`/`_action_segment_create_many` used to set a new
    segment's `provenance_kind` from `pass_row.provenance_kind` (the PASS's
    maker), not from who actually acted. The rule slice 1 set (and the
    agent surface already applies for claims/annotations, #4868/#4869):
    the maker is set by the engine from WHO ACTED -- a real actor with no
    run behind it is a person, a run behind it is a workflow, nothing
    given is honestly unknown -- never inherited from the container, never
    client-supplied. `segments.py`'s own `_provenance_kind_from_ctx` is
    that ONE derivation for this domain (already used for match
    proposals); `segment.create`/`.create_many` now call it too, instead
    of a second copy of the rule."""

    def test_a_person_creating_inside_a_machine_pass_is_stored_as_human(self, client, db):
        from fichero_server.actions.registry import ActionContext, registry

        doc = _make_doc(db)
        machine_pass = _create_pass(client, doc.id, run_id="run-abc")
        assert db.get(SegmentPass, machine_pass["id"]).provenance_kind == "workflow"

        ctx = ActionContext(actor="daniel", library_path=str(db.path.parent))
        result = registry.invoke(
            db, "segment.create",
            {
                "document_id": doc.id, "pass_id": machine_pass["id"], "kind": "word",
                "anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]},
            },
            ctx,
        )
        segment_id = result.result["segment_ids"][0]
        assert db.get(Segment, segment_id).provenance_kind == "human"

    def test_a_workflow_run_creating_inside_a_human_pass_is_stored_as_workflow(self, client, db):
        from fichero_server.actions.registry import ActionContext, registry

        doc = _make_doc(db)
        human_pass = _create_pass(client, doc.id)
        assert db.get(SegmentPass, human_pass["id"]).provenance_kind == "human"

        ctx = ActionContext(actor="worker", run_id="run-xyz", library_path=str(db.path.parent))
        result = registry.invoke(
            db, "segment.create_many",
            {
                "document_id": doc.id, "pass_id": human_pass["id"],
                "segments": [
                    {"kind": "word", "anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}},
                ],
            },
            ctx,
        )
        segment_id = result.result["segment_ids"][0]
        assert db.get(Segment, segment_id).provenance_kind == "workflow"

    def test_a_bystander_with_no_run_and_no_real_actor_is_stored_as_unknown(self, client, db):
        """Neither a run nor a real actor behind the write: honestly
        `unknown`, never a trusting default of either kind -- same posture
        as `_provenance_kind_from_ctx` everywhere else in this file."""
        from fichero_server.actions.registry import ActionContext, registry

        doc = _make_doc(db)
        machine_pass = _create_pass(client, doc.id, run_id="run-abc")

        ctx = ActionContext(actor="", library_path=str(db.path.parent))
        result = registry.invoke(
            db, "segment.create",
            {
                "document_id": doc.id, "pass_id": machine_pass["id"], "kind": "word",
                "anchor": {"document_id": doc.id, "rect": [0.3, 0.3, 0.1, 0.1]},
            },
            ctx,
        )
        segment_id = result.result["segment_ids"][0]
        assert db.get(Segment, segment_id).provenance_kind == "unknown"

    def test_a_caller_cannot_supply_provenance_kind_directly(self, client, db):
        doc = _make_doc(db)
        pass_body = _create_pass(client, doc.id)
        r = client.post("/api/segments", json={
            "document_id": doc.id, "pass_id": pass_body["id"], "kind": "word",
            "anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]},
            "provenance_kind": "workflow",
        })
        assert r.status_code == 422


class TestRecordPerSegment:
    def test_lines_of_this_pass_and_children_of_this_region_are_single_filtered_queries(
        self, client, db,
    ):
        """source.store.record-per-segment."""
        doc = _make_doc(db)
        pass_body = _create_pass(client, doc.id)
        region = _create_segment(
            client, document_id=doc.id, pass_id=pass_body["id"], kind="region",
        ).json()
        line_1 = _create_segment(
            client, document_id=doc.id, pass_id=pass_body["id"], kind="line",
            parent_segment_id=region["id"],
        ).json()
        line_2 = _create_segment(
            client, document_id=doc.id, pass_id=pass_body["id"], kind="line",
            parent_segment_id=region["id"],
        ).json()
        _create_segment(client, document_id=doc.id, pass_id=pass_body["id"], kind="word").json()

        lines = db.query(Segment, pass_id=pass_body["id"], kind="line")
        assert {s.id for s in lines} == {line_1["id"], line_2["id"]}

        children = db.query(Segment, parent_segment_id=region["id"])
        assert {s.id for s in children} == {line_1["id"], line_2["id"]}


class TestRefusals:
    def test_pass_id_from_another_document_is_refused(self, client, db):
        doc_1 = _make_doc(db, "one.jpg")
        doc_2 = _make_doc(db, "two.jpg")
        other_pass = _create_pass(client, doc_2.id)

        r = _create_segment(client, document_id=doc_1.id, pass_id=other_pass["id"])
        assert r.status_code == 409

    def test_parent_segment_in_another_pass_is_refused(self, client, db):
        doc = _make_doc(db)
        pass_1 = _create_pass(client, doc.id)
        pass_2 = _create_pass(client, doc.id)
        parent = _create_segment(client, document_id=doc.id, pass_id=pass_1["id"]).json()

        r = _create_segment(
            client, document_id=doc.id, pass_id=pass_2["id"], parent_segment_id=parent["id"],
        )
        assert r.status_code == 409

    def test_anchor_document_id_mismatch_is_refused(self, client, db):
        doc = _make_doc(db)
        pass_body = _create_pass(client, doc.id)
        r = _create_segment(
            client, document_id=doc.id, pass_id=pass_body["id"],
            anchor={"document_id": "some-other-doc", "rect": [0.1, 0.1, 0.1, 0.1]},
        )
        assert r.status_code == 422

    def test_a_legacy_id_anywhere_is_refused(self, client, db):
        """source.seam.provisional-ids-refused, extended to slice 3's
        writes."""
        r = client.post(
            "/api/segments/passes",
            json={"document_id": "legacy:some-artifact", "name": "n"},
        )
        assert r.status_code == 422
        assert "provisional" in r.json()["detail"]


class TestPassDeleteAndRestore:
    def test_deleted_pass_and_its_segments_still_readable_but_pass_marked_deleted(self, client, db):
        doc = _make_doc(db)
        pass_body = _create_pass(client, doc.id)
        _create_segment(client, document_id=doc.id, pass_id=pass_body["id"])

        r = client.delete(f"/api/segments/passes/{pass_body['id']}")
        assert r.status_code == 200, r.text
        stored = db.get(SegmentPass, pass_body["id"])
        assert stored.deleted_at is not None
        # The row is never removed -- soft delete only.
        assert db.get(SegmentPass, pass_body["id"]) is not None

    def test_deleted_pass_is_excluded_from_the_seam(self, client, db):
        doc = _make_doc(db)
        pass_body = _create_pass(client, doc.id)
        _create_segment(client, document_id=doc.id, pass_id=pass_body["id"])

        before = client.get(f"/api/segments/document/{doc.id}").json()
        assert len(before["passes"]) == 1

        client.delete(f"/api/segments/passes/{pass_body['id']}")

        after = client.get(f"/api/segments/document/{doc.id}").json()
        assert after["passes"] == []
        assert after["segments"] == []


class TestCreateMany:
    def test_create_many_uses_save_many_and_returns_every_segment(self, client, db):
        doc = _make_doc(db)
        pass_body = _create_pass(client, doc.id)
        r = client.post(
            "/api/segments/bulk",
            json={
                "document_id": doc.id,
                "pass_id": pass_body["id"],
                "segments": [
                    {"kind": "word", "anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}},
                    {"kind": "word", "anchor": {"document_id": doc.id, "rect": [0.3, 0.3, 0.1, 0.1]}},
                ],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["segments"]) == 2
        assert len(db.query(Segment, pass_id=pass_body["id"])) == 2

    def test_create_many_is_one_atomic_action_a_failed_audit_write_leaves_no_rows(
        self, client, db, monkeypatch,
    ):
        """The real break the review found: `save_many` used to open, commit
        and close its OWN transaction before the audit row was written, so a
        failed audit write left segment rows with no audit record and no
        undo. `save_many` now joins the ambient `db.transaction()`, so
        `segment.create_many` is genuinely one atomic action."""
        import fichero_server.actions.audit_chain as audit_chain

        doc = _make_doc(db)
        pass_body = _create_pass(client, doc.id)

        def _boom(*_a, **_k):
            raise RuntimeError("audit write failed")

        monkeypatch.setattr(audit_chain, "save_chained_audit", _boom)

        with pytest.raises(RuntimeError, match="audit write failed"):
            client.post(
                "/api/segments/bulk",
                json={
                    "document_id": doc.id,
                    "pass_id": pass_body["id"],
                    "segments": [
                        {"kind": "word", "anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}},
                        {"kind": "word", "anchor": {"document_id": doc.id, "rect": [0.3, 0.3, 0.1, 0.1]}},
                    ],
                },
            )

        assert db.query(Segment, pass_id=pass_body["id"]) == []


class TestUndo:
    def test_undoing_segment_create_removes_exactly_that_segment(self, client, db):
        doc = _make_doc(db)
        pass_body = _create_pass(client, doc.id)
        segment = _create_segment(client, document_id=doc.id, pass_id=pass_body["id"]).json()

        audits = db.query(ActionAudit)
        create_audit = [a for a in audits if a.action_name == "segment.create"][-1]

        r = client.post(f"/api/actions/audit/{create_audit.id}/undo")
        assert r.status_code == 200, r.text
        assert db.get(Segment, segment["id"]).deleted_at is not None


class TestAuditPayloadsCarryNoText:
    def test_no_audit_row_of_these_actions_contains_a_content_or_text_key(self, client, db):
        """The audit's params/before/after sit inside the tamper-evident
        HMAC chain and can never be rewritten -- so a purge could never
        reach a researcher's words if they were audited (#4921 notes: "What
        an audit record may carry"). Segment/pass actions record ids, kinds
        and geometry, never a reading's text."""
        doc = _make_doc(db)
        pass_body = _create_pass(client, doc.id)
        _create_segment(client, document_id=doc.id, pass_id=pass_body["id"], kind_raw="ModelLabel")
        client.post(
            "/api/segments/bulk",
            json={
                "document_id": doc.id, "pass_id": pass_body["id"],
                "segments": [
                    {"kind": "word", "anchor": {"document_id": doc.id, "rect": [0.5, 0.5, 0.1, 0.1]}},
                ],
            },
        )
        client.delete(f"/api/segments/passes/{pass_body['id']}")

        audits = [a for a in db.query(ActionAudit) if a.action_name.startswith(("segment.", "pass."))]
        assert audits, "expected at least one segment/pass audit row"
        for audit in audits:
            for payload in (audit.params, audit.before, audit.after):
                if not payload:
                    continue
                assert "content" not in payload, (audit.action_name, payload)
                assert "text" not in payload, (audit.action_name, payload)


class TestTheSeamReadsBothRealAndLegacy:
    def test_seam_returns_rows_for_a_converted_document_and_boxes_for_an_unconverted_one(
        self, client, db,
    ):
        """The seam now reads both -- in the SAME response shape."""
        from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult

        legacy_doc = _make_doc(db, "legacy.jpg")
        geometry = OCRGeometryResult(
            text="alpha", provider="apple_vision",
            boxes=[OCRGeometryBox(text="alpha", bbox=[0.1, 0.1, 0.2, 0.05], level="word")],
        )
        artifact = Artifact(document_id=legacy_doc.id, artifact_type="regions", content="alpha", ocr_geometry=geometry)
        db.save(artifact)

        real_doc = _make_doc(db, "real.jpg")
        pass_body = _create_pass(client, real_doc.id)
        segment = _create_segment(client, document_id=real_doc.id, pass_id=pass_body["id"]).json()

        legacy_body = client.get(f"/api/segments/document/{legacy_doc.id}").json()
        real_body = client.get(f"/api/segments/document/{real_doc.id}").json()

        assert legacy_body["segments"][0]["provisional"] is True
        assert legacy_body["segments"][0]["id"] == f"legacy:{artifact.id}:0"
        assert real_body["segments"][0]["provisional"] is False
        assert real_body["segments"][0]["id"] == segment["id"]
        # Same response shape either way.
        assert set(legacy_body.keys()) == set(real_body.keys())
        assert set(legacy_body["segments"][0].keys()) == set(real_body["segments"][0].keys())


class TestRealPassIsDrawable:
    """test-audit B2, 2026-09-20: for a REAL (non-legacy) row the seam used
    to report `box_index=None` and `artifact_type=None` unconditionally,
    which is exactly what the app refuses to draw (a pass whose box indexes
    are not dense `0..count` is refused; a pass with no artifact_type is
    excluded from ranking). Per the spec (build-notes-identity-and-storage.md,
    the slice 1 seam's own docstring, and App slice A stage 2's "a pass made
    from an artifact carries that artifact's type"): the seam reports the
    RESOLVED read order (`metadata['box_index']` when a converted box
    recorded one, else `created_at` then `id`) as a dense `box_index`, and a
    pass with a `source_artifact_id` carries that artifact's `artifact_type`."""

    def test_real_segments_in_a_pass_get_a_dense_box_index_in_read_order(self, client, db):
        doc = _make_doc(db)
        pass_body = _create_pass(client, doc.id)
        # Created out of any spatial order -- box_index must reflect the
        # RESOLVED read order (created_at then id here; none of these rows
        # set metadata["box_index"]), not client-supplied position.
        made = [
            _create_segment(
                client, document_id=doc.id, pass_id=pass_body["id"],
                anchor={"document_id": doc.id, "rect": [0.1 * i, 0.1 * i, 0.05, 0.05]},
            ).json()
            for i in range(4)
        ]

        body = client.get(f"/api/segments/document/{doc.id}").json()
        segments = [s for s in body["segments"] if s["pass_id"] == pass_body["id"]]
        assert [s["box_index"] for s in segments] == [0, 1, 2, 3]
        assert [s["id"] for s in segments] == [s["id"] for s in made]

    def test_box_index_is_scoped_per_pass_not_across_the_whole_document(self, client, db):
        doc = _make_doc(db)
        pass_a = _create_pass(client, doc.id, name="pass-a")
        pass_b = _create_pass(client, doc.id, name="pass-b")
        _create_segment(client, document_id=doc.id, pass_id=pass_a["id"])
        _create_segment(client, document_id=doc.id, pass_id=pass_b["id"])
        _create_segment(client, document_id=doc.id, pass_id=pass_b["id"])

        body = client.get(f"/api/segments/document/{doc.id}").json()
        by_pass: dict[str, list[int]] = {}
        for s in body["segments"]:
            by_pass.setdefault(s["pass_id"], []).append(s["box_index"])
        assert by_pass[pass_a["id"]] == [0]
        assert by_pass[pass_b["id"]] == [0, 1]

    def test_a_pass_made_from_an_artifact_carries_that_artifacts_type(self, client, db):
        from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult

        doc = _make_doc(db)
        geometry = OCRGeometryResult(
            text="alpha", provider="apple_vision",
            boxes=[OCRGeometryBox(text="alpha", bbox=[0.1, 0.1, 0.2, 0.05], level="word")],
        )
        artifact = Artifact(
            document_id=doc.id, artifact_type="regions", content="alpha", ocr_geometry=geometry,
        )
        db.save(artifact)

        pass_body = _create_pass(client, doc.id, source_artifact_id=artifact.id)

        body = client.get(f"/api/segments/document/{doc.id}").json()
        real_pass = next(p for p in body["passes"] if p["id"] == pass_body["id"])
        assert real_pass["artifact_type"] == "regions"

    def test_a_pass_with_no_source_artifact_reports_no_artifact_type(self, client, db):
        """Not invented: the spec only says a pass MADE FROM an artifact
        carries its type. A from-scratch pass (no source_artifact_id) has
        nothing to carry, and stays `None` -- not a guess."""
        doc = _make_doc(db)
        pass_body = _create_pass(client, doc.id)

        body = client.get(f"/api/segments/document/{doc.id}").json()
        real_pass = next(p for p in body["passes"] if p["id"] == pass_body["id"])
        assert real_pass["artifact_type"] is None


def _make_segments(document_id: str, pass_id: str, count: int, *, kinds: tuple[str, ...] = ("word", "line")):
    from fichero_server.models.anchors import SourceAnchor
    from fichero_server.models.knowledge import ProvenanceKind
    from fichero_server.models.segments import bbox_and_tile_from_anchor

    rows = []
    for i in range(count):
        kind = kinds[i % len(kinds)]
        # Spread rects across the image so segments land in every tile of
        # the 8x8 grid, not all in one -- a real page's boxes are spread out,
        # not stacked at the same point.
        frac = (i % 64) / 64.0
        anchor = SourceAnchor(document_id=document_id, rect=[frac, frac, 0.01, 0.01])
        x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
        rows.append(Segment(
            document_id=document_id, pass_id=pass_id, kind=kind,
            anchor=anchor, bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h, tile=tile,
            doc_kind=f"{document_id}:{kind}",
            provenance_kind=ProvenanceKind.workflow,
        ))
    return rows


class TestBoundedReadsCorrectness:
    """source.store.bounded-reads' CORRECTNESS half -- never marked slow
    (test-audit B1, 2026-09-20): these four run in a few milliseconds each
    and pin the by-area review fixes (the wide-segment and half-tile-
    straddler cases) that the timing class's blanket `@pytest.mark.slow`
    had switched off in every ordinary gate/CI run (`-m "not slow"` /
    `-k "not slow"`). Proven by the audit: removing the half-tile growth
    fix left the (then-slow-tagged) suite at 50 passed, 7 deselected."""

    def test_area_returns_a_wide_segment_centred_outside_it_but_not_one_wholly_outside(
        self, client, db,
    ):
        """#4921 review: a segment is filed under the tile of its CENTRE
        only, so a wide segment covering the queried area but centred
        outside it must still come back -- true box intersection, not tile
        membership alone. A segment wholly outside the area must not."""
        from fichero_server.models.anchors import SourceAnchor
        from fichero_server.models.knowledge import ProvenanceKind
        from fichero_server.models.segments import bbox_and_tile_from_anchor

        doc = _make_doc(db, name="area-intersection.jpg")
        pass_row = SegmentPass(document_id=doc.id, name="area", provenance_kind=ProvenanceKind.workflow)
        db.save(pass_row)

        # As wide as the page, centred at y=0.9 -- its tile of centre is
        # nowhere near the queried area up at the top of the page, but its
        # box still spans down through it.
        wide_anchor = SourceAnchor(document_id=doc.id, rect=[0.0, 0.05, 1.0, 0.9])
        wx, wy, ww, wh, wtile = bbox_and_tile_from_anchor(wide_anchor)
        wide_segment = Segment(
            document_id=doc.id, pass_id=pass_row.id, kind="region", anchor=wide_anchor,
            bbox_x=wx, bbox_y=wy, bbox_w=ww, bbox_h=wh, tile=wtile,
            doc_kind=f"{doc.id}:region", provenance_kind=ProvenanceKind.workflow,
        )

        # Wholly outside the queried area: bottom-right corner.
        outside_anchor = SourceAnchor(document_id=doc.id, rect=[0.9, 0.9, 0.05, 0.05])
        ox, oy, ow, oh, otile = bbox_and_tile_from_anchor(outside_anchor)
        outside_segment = Segment(
            document_id=doc.id, pass_id=pass_row.id, kind="region", anchor=outside_anchor,
            bbox_x=ox, bbox_y=oy, bbox_w=ow, bbox_h=oh, tile=otile,
            doc_kind=f"{doc.id}:region", provenance_kind=ProvenanceKind.workflow,
        )
        db.save_many([wide_segment, outside_segment])

        r = client.get(f"/api/segments/document/{doc.id}", params={"area": "0,0,0.1,0.1"})
        assert r.status_code == 200
        ids = {s["id"] for s in r.json()["segments"]}
        assert wide_segment.id in ids
        assert outside_segment.id not in ids

    def test_area_returns_a_small_segment_straddling_the_tile_edge_into_the_area(
        self, client, db,
    ):
        """#4921 third look: a segment NO LARGER than a tile, centred just
        outside every tile the bare rectangle touches, can still reach into
        the rectangle -- its box extends up to half a tile from its centre.
        The candidate query must grow the queried rectangle by half a tile
        on every side before finding candidate tiles, or this segment is
        never a candidate at all (`rects_intersect` never even sees it)."""
        from fichero_server.models.anchors import SourceAnchor
        from fichero_server.models.knowledge import ProvenanceKind
        from fichero_server.models.segments import TILE_SIZE, bbox_and_tile_from_anchor

        doc = _make_doc(db, name="straddler.jpg")
        pass_row = SegmentPass(document_id=doc.id, name="straddler", provenance_kind=ProvenanceKind.workflow)
        db.save(pass_row)

        # Queried area: the top-left tile only, [0, 0, 0.1, 0.1].
        area = "0,0,0.1,0.1"

        # Centred at (0.13, 0.02) -- tile x1y0, NOT one of the tiles the bare
        # rectangle touches (x0y0 only) -- but the box (width 0.08, well
        # under one tile's 0.125) reaches back to x=0.09, inside the area.
        straddler_anchor = SourceAnchor(document_id=doc.id, rect=[0.09, 0.01, 0.08, 0.02])
        assert straddler_anchor.rect[2] < TILE_SIZE and straddler_anchor.rect[3] < TILE_SIZE
        sx, sy, sw, sh, stile = bbox_and_tile_from_anchor(straddler_anchor)
        straddler = Segment(
            document_id=doc.id, pass_id=pass_row.id, kind="word", anchor=straddler_anchor,
            bbox_x=sx, bbox_y=sy, bbox_w=sw, bbox_h=sh, tile=stile,
            doc_kind=f"{doc.id}:word", provenance_kind=ProvenanceKind.workflow,
        )
        db.save(straddler)

        r = client.get(f"/api/segments/document/{doc.id}", params={"area": area})
        assert r.status_code == 200
        assert straddler.id in {s["id"] for s in r.json()["segments"]}

        # The same segment moved wholly outside the area must not come back.
        moved_anchor = SourceAnchor(document_id=doc.id, rect=[0.5, 0.5, 0.08, 0.02])
        mx, my, mw, mh, mtile = bbox_and_tile_from_anchor(moved_anchor)
        moved = Segment(
            document_id=doc.id, pass_id=pass_row.id, kind="word", anchor=moved_anchor,
            bbox_x=mx, bbox_y=my, bbox_w=mw, bbox_h=mh, tile=mtile,
            doc_kind=f"{doc.id}:word", provenance_kind=ProvenanceKind.workflow,
        )
        db.save(moved)
        r2 = client.get(f"/api/segments/document/{doc.id}", params={"area": area})
        assert moved.id not in {s["id"] for s in r2.json()["segments"]}

    def test_area_rejects_malformed_input(self, client, db):
        doc = _make_doc(db, name="bad-area.jpg")
        r = client.get(f"/api/segments/document/{doc.id}", params={"area": "not,a,rect"})
        assert r.status_code == 422

    def test_a_read_with_no_document_id_is_refused(self, client):
        """Structural, not a new check: `doc_id` is a required path
        parameter, so the route simply does not match without one."""
        r = client.get("/api/segments/document/")
        assert r.status_code == 404


@pytest.mark.slow
class TestBoundedReadsPerformance:
    """source.store.bounded-reads' TIMED half -- the two `< 200ms`
    assertions and the one honest, unasserted measurement. Excluded with
    `-m "not slow"` on a loaded machine or in CI; the CORRECTNESS tests
    that used to live in this class (test-audit B1) never carried a
    timing dependency and are not marked slow any more."""

    def test_one_page_one_kind_at_200k_segments_in_the_source_returns_in_under_200ms(
        self, client, db,
    ):
        """200,000 segments spread as a real source is: 500 page documents
        of 400 segments each. The route answers for ONE page, one kind."""
        from fichero_server.models.knowledge import ProvenanceKind

        target_doc = None
        for page_num in range(500):
            doc = _make_doc(db, name=f"page-{page_num}.jpg")
            if page_num == 250:
                target_doc = doc
            pass_row = SegmentPass(document_id=doc.id, name="bulk", provenance_kind=ProvenanceKind.workflow)
            db.save(pass_row)
            db.save_many(_make_segments(doc.id, pass_row.id, 400))

        started = time.perf_counter()
        r = client.get(f"/api/segments/document/{target_doc.id}", params={"kind": "word"})
        elapsed_ms = (time.perf_counter() - started) * 1000
        assert r.status_code == 200
        assert len(r.json()["segments"]) == 200  # half of 400 are "word"
        print(f"\n[bounded-reads] one page, one kind, 200,000 segments in the source: {elapsed_ms:.1f} ms")
        assert elapsed_ms < 200, f"took {elapsed_ms:.1f} ms, wanted < 200 ms"

    def test_dense_page_by_kind_and_by_area_returns_in_under_200ms(self, client, db):
        """The editor's case: 20,000 segments on ONE page. By kind AND by
        area (a rectangle, `area=x,y,w,h`) together, through the route."""
        from fichero_server.models.knowledge import ProvenanceKind

        doc = _make_doc(db, name="dense.jpg")
        pass_row = SegmentPass(document_id=doc.id, name="dense", provenance_kind=ProvenanceKind.workflow)
        db.save(pass_row)
        db.save_many(_make_segments(doc.id, pass_row.id, 20_000))

        started = time.perf_counter()
        r = client.get(
            f"/api/segments/document/{doc.id}", params={"kind": "word", "area": "0,0,0.125,0.125"},
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        assert r.status_code == 200
        assert r.json()["segments"]  # at least one segment in this area
        assert all(s["kind"] == "word" for s in r.json()["segments"])
        print(f"[bounded-reads] dense page (20,000), one kind + one area: {elapsed_ms:.1f} ms")
        assert elapsed_ms < 200, f"took {elapsed_ms:.1f} ms, wanted < 200 ms"

    def test_a_whole_dense_page_in_one_read_is_measured_not_asserted(self, client, db):
        """A whole dense page (no kind, no area filter) is the ORM's honest
        cost at this row count -- reported, never asserted (slice 3b, a
        lean read path with no intermediate model, is what would bound
        this; not built now)."""
        from fichero_server.models.knowledge import ProvenanceKind

        doc = _make_doc(db, name="dense-whole.jpg")
        pass_row = SegmentPass(document_id=doc.id, name="dense", provenance_kind=ProvenanceKind.workflow)
        db.save(pass_row)
        db.save_many(_make_segments(doc.id, pass_row.id, 20_000))

        started = time.perf_counter()
        r = client.get(f"/api/segments/document/{doc.id}")
        elapsed_ms = (time.perf_counter() - started) * 1000
        assert r.status_code == 200
        assert len(r.json()["segments"]) == 20_000
        print(f"[bounded-reads] a WHOLE dense page (20,000), no filter: {elapsed_ms:.1f} ms (not asserted)")
