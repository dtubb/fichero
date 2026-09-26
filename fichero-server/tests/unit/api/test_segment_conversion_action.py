"""Slice 6 (#4924) -- `segment.convert_and_edit`, the conversion half.

One audited, atomic, undoable action: a page's boxes become lasting
segments, exactly once, and nothing a person can see changes.

The edit half is step 5, so every invocation here is the EAGER form named
in assumption A1 -- one document, no edit. That is not a weaker test: A1's
whole claim is that a page converted eagerly and a page converted lazily
end up byte-identical, so if the eager form is right the lazy one converts
the same rows.
"""

from __future__ import annotations

import json
import threading

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_conversion import (
    AlreadyConverted,
    ArtifactNotOnThisDocument,
    NothingToConvert,
    SegmentConvertAndEditParams,
    is_converted,
    live_rows_in_order,
)
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import ActionAudit, Artifact, DocType, Document, FileType, Status
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import (
    Segment,
    SegmentPass,
    SegmentVersion,
    converted_pass_id,
    converted_segment_id,
)

pytestmark = pytest.mark.source_model


def _ctx() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


#: The smallest real edit: move box 0 where it already is. Used where a
#: test needs the WORKING-pass form (`artifact_id` and `edit` together)
#: without the edit itself being what is under test.
A_TRIVIAL_EDIT = {"op": "move", "indices": [0], "bbox": [0.1, 0.1, 0.2, 0.02]}


def _invoke(db, **params):
    """The EAGER form of assumption A1 by default: one document, no edit.

    `artifact_id` names the WORKING pass and only means anything with an
    edit beside it, so the action refuses one without the other. Tests that
    are about CONVERSION use this; tests about the edit go through the PUT
    route or pass both.
    """
    return registry.invoke(db, "segment.convert_and_edit", params, _ctx())


def _invoke_action(db, name: str, params: dict):
    return registry.invoke(db, name, params, _ctx())


def _make_doc(db, name: str = "page.jpg") -> Document:
    doc = Document(
        name=name, doc_type=DocType.file, file_type=FileType.image,
        path=f"/path/{name}", status=Status.completed,
    )
    db.save(doc)
    return doc


def _block(count: int = 3, hand_drawn_at: int | None = None) -> OCRGeometryResult:
    boxes = []
    for i in range(count):
        extra = {}
        if hand_drawn_at is not None and i == hand_drawn_at:
            extra = {"provider": "user", "source": "manual"}
        boxes.append(
            OCRGeometryBox(
                text=f"w{i}", bbox=[0.1, 0.9 * i / max(1, count), 0.2, 0.02],
                level="line", page_index=0, **extra,
            )
        )
    return OCRGeometryResult(
        provider="qwen", model="qwen-vl-max",
        text=" ".join(f"w{i}" for i in range(count)), boxes=boxes,
    )


def _artifact(db, doc, block=None, artifact_type="transcription") -> Artifact:
    artifact = Artifact(
        document_id=doc.id, artifact_type=artifact_type,
        provider="qwen", model="qwen-vl-max",
        ocr_geometry=block if block is not None else _block(),
    )
    db.save(artifact)
    return artifact


def _seam(client, doc_id: str):
    r = client.get(f"/api/segments/document/{doc_id}")
    assert r.status_code == 200, r.text
    return r.json()


class TestIdsOnFirstEdit:
    """`source.store.ids-on-first-edit`."""

    def test_converting_makes_a_pass_for_every_result_with_boxes(self, db):
        doc = _make_doc(db)
        a1 = _artifact(db, doc, _block(3))
        a2 = _artifact(db, doc, _block(2), artifact_type="regions")
        result = _invoke(db, document_id=doc.id)

        assert len(result.result["pass_ids"]) == 2
        assert result.result["segment_count"] == 5
        for artifact in (a1, a2):
            reread = db.get(Artifact, artifact.id)
            assert reread.geometry_superseded_by_pass_id == converted_pass_id(artifact.id)
            assert db.get(SegmentPass, converted_pass_id(artifact.id)) is not None

    def test_the_ids_are_the_repeatable_ones(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc, _block(3))
        _invoke(db, document_id=doc.id)
        for i in range(3):
            assert db.get(Segment, converted_segment_id(artifact.id, i)) is not None

    def test_reading_a_page_converts_nothing(self, db, client):
        """Conversion is lazy, on a first EDIT -- never on open."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        for _ in range(10):
            _seam(client, doc.id)
        assert db.get(Artifact, artifact.id).geometry_superseded_by_pass_id is None
        assert db.query(SegmentPass, document_id=doc.id) == []

    def test_a_second_eager_conversion_finds_nothing_to_convert(self, db):
        doc = _make_doc(db)
        _artifact(db, doc)
        _invoke(db, document_id=doc.id)
        with pytest.raises(NothingToConvert):
            _invoke(db, document_id=doc.id)

    def test_naming_an_already_converted_working_artifact_with_no_edit_is_refused(
        self, db
    ):
        """`artifact_id` with no edit is not the eager form and not an
        edit: it says nothing this action can act on."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _invoke(db, document_id=doc.id)
        with pytest.raises(Exception) as caught:
            _invoke(db, document_id=doc.id, artifact_id=artifact.id)
        assert "come together" in str(caught.value)

    def test_editing_an_already_converted_page_again_just_edits_it(self, db):
        """The ordinary second and later edit, and the branch a REDO takes:
        the page is already converted, so only the edit is applied."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _invoke(db, document_id=doc.id)
        result = _invoke(
            db, document_id=doc.id, artifact_id=artifact.id, edit=A_TRIVIAL_EDIT
        )
        assert result.result["artifact_ids"] == [], "nothing left to convert"
        assert result.result["edit"]["action"] == "segment.update"

    def test_a_result_that_arrives_after_conversion_is_converted_next_time(self, db):
        """Per artifact, not per document: a machine run after conversion
        writes a block and is converted by the NEXT edit. A second
        conversion on one document is normal, not refused."""
        doc = _make_doc(db)
        first = _artifact(db, doc, _block(3))
        _invoke(db, document_id=doc.id)
        later = _artifact(db, doc, _block(2), artifact_type="regions")

        result = _invoke(db, document_id=doc.id)
        assert result.result["artifact_ids"] == [later.id]
        assert result.result["segment_count"] == 2

    def test_a_document_with_nothing_to_convert_says_so(self, db):
        doc = _make_doc(db)
        with pytest.raises(NothingToConvert):
            _invoke(db, document_id=doc.id)

    def test_a_result_with_an_empty_box_list_is_left_alone(self, db):
        """It would make a pass with nothing in it, and the seam already
        answers for it as a provisional pass."""
        doc = _make_doc(db)
        empty = _artifact(db, doc, OCRGeometryResult(provider="user", boxes=[]))
        real = _artifact(db, doc, _block(2))
        result = _invoke(db, document_id=doc.id)
        assert result.result["artifact_ids"] == [real.id]
        assert db.get(Artifact, empty.id).geometry_superseded_by_pass_id is None


class TestConversionChangesNothingYouCanSee:
    """`source.store.conversion-changes-nothing-seen` -- the master test,
    through the real route and the real action.

    Run WITHOUT `area`: the seam's legacy branch ignores that filter while
    the real-row branch applies it (#4985), which would confound the
    comparison rather than test it.
    """

    @pytest.mark.parametrize(
        "block",
        [
            pytest.param(_block(1), id="one-box"),
            pytest.param(_block(5), id="several-boxes"),
            pytest.param(_block(4, hand_drawn_at=2), id="a-hand-drawn-box-inside"),
            pytest.param(
                OCRGeometryResult(
                    provider="qwen", text="a b",
                    boxes=[
                        OCRGeometryBox(text="a", bbox=[0.1, 0.1, 0.2, 0.05], char_start=0, char_end=1),
                        OCRGeometryBox(text="", bbox=[0.5, 0.5, 0.0, 0.0]),
                        OCRGeometryBox(text="b", bbox=[0.1, 0.3, 0.2, 0.05], char_start=2, char_end=3),
                    ],
                ),
                id="an-undrawable-box",
            ),
            pytest.param(
                OCRGeometryResult(
                    provider="qwen", text="p1 p2",
                    boxes=[
                        OCRGeometryBox(text="p1", bbox=[0.1, 0.1, 0.2, 0.05], page_index=0),
                        OCRGeometryBox(text="p2", bbox=[0.1, 0.2, 0.2, 0.05], page_index=3),
                    ],
                ),
                id="a-multi-page-pdf-result",
            ),
            pytest.param(
                OCRGeometryResult(
                    provider="", text="",
                    boxes=[OCRGeometryBox(text="x", bbox=[0.1, 0.1, 0.2, 0.05])],
                ),
                id="a-result-with-no-provider-or-model",
            ),
            pytest.param(
                OCRGeometryResult(
                    provider="kraken", rendition_id="rend-crop-9",
                    boxes=[
                        OCRGeometryBox(
                            text="l", bbox=[0.1, 0.1, 0.4, 0.05], level="line",
                            metadata={"polygon_px": [[10, 10], [50, 10], [50, 20], [10, 20]],
                                      "baseline_px": [[10, 19], [50, 19]],
                                      "pixel_frame": [100, 100]},
                        )
                    ],
                ),
                id="polygons-and-baselines",
            ),
        ],
    )
    def test_the_seam_answers_the_same_but_for_id_pass_id_and_provisional(
        self, db, client, block
    ):
        doc = _make_doc(db)
        artifact = _artifact(db, doc, block)
        if not block.provider:
            # A result with no provider and no model: the pass's maker is
            # `unknown`, and the artifact must say so too or the before and
            # after would differ for a reason that is not conversion's.
            artifact.provider = None
            artifact.model = None
            db.save(artifact)
        before = _seam(client, doc.id)
        _invoke(db, document_id=doc.id)
        after = _seam(client, doc.id)

        assert len(after["passes"]) == len(before["passes"])
        assert len(after["segments"]) == len(before["segments"])
        for b, a in zip(before["segments"], after["segments"], strict=True):
            # ONLY these three may differ. `source_artifact_id` is no longer
            # among them: the seam knows the pass's source artifact and
            # fills it, so a converted segment names the same artifact the
            # provisional one named (#4924 review).
            for field in ("id", "pass_id", "provisional"):
                b.pop(field), a.pop(field)
            # Metadata is compared MINUS the two keys conversion adds, not
            # popped whole -- popping it would let a lost or changed key
            # through unnoticed.
            added_index = a["metadata"].pop("box_index")
            added_page = a["metadata"].pop("page_index", None)
            assert added_index == b["box_index"]
            assert added_page == b["page_index"]
            assert a == b
        for b, a in zip(before["passes"], after["passes"], strict=True):
            for field in ("id", "provisional"):
                b.pop(field), a.pop(field)
            assert a == b

    def test_two_results_on_one_page_keep_their_order_through_the_seam(self, db, client):
        """Pass ORDER is what is at stake with two results, and it was
        tested at the model level only. The seam sorts passes by
        `(created_at, id)`, so a pass stamped at conversion time rather
        than with the artifact's own time would reorder the page -- a
        difference a person can see."""
        import datetime as dt

        doc = _make_doc(db)
        older = _artifact(db, doc, _block(2))
        newer = _artifact(db, doc, _block(3), )
        older.created_at = dt.datetime(2019, 3, 2, 9, 0, tzinfo=dt.timezone.utc)
        newer.created_at = dt.datetime(2021, 7, 8, 14, 0, tzinfo=dt.timezone.utc)
        db.save(older)
        db.save(newer)

        before = _seam(client, doc.id)
        assert [p["source_artifact_id"] for p in before["passes"]] == [older.id, newer.id]
        assert [s["text"] for s in before["segments"]] == ["w0", "w1", "w0", "w1", "w2"]

        _invoke(db, document_id=doc.id)
        after = _seam(client, doc.id)

        assert [p["source_artifact_id"] for p in after["passes"]] == [older.id, newer.id]
        assert [s["text"] for s in after["segments"]] == ["w0", "w1", "w0", "w1", "w2"]
        assert all(p["provisional"] is False for p in after["passes"])

    def test_the_artifact_row_is_byte_equal_but_for_the_marker(self, db):
        """`Artifact` has no `updated_at`, so the whole dump is the
        assertion -- a stronger one anyway."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc, _block(4))
        before = db.get(Artifact, artifact.id).model_dump(mode="json")
        _invoke(db, document_id=doc.id)
        after = db.get(Artifact, artifact.id).model_dump(mode="json")

        assert before.pop("geometry_superseded_by_pass_id") is None
        assert after.pop("geometry_superseded_by_pass_id") == converted_pass_id(artifact.id)
        assert after == before, "the machine's own record must not be touched"


class TestConvertedBoxesKeepTheirMaker:
    """`source.store.converted-boxes-keep-their-maker`."""

    def test_fifty_machine_boxes_and_one_hand_drawn(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc, _block(50, hand_drawn_at=17))
        _invoke(db, document_id=doc.id)

        rows = live_rows_in_order(db, converted_pass_id(artifact.id))
        assert len(rows) == 50
        machine = [r for r in rows if r.provenance_kind is ProvenanceKind.workflow]
        human = [r for r in rows if r.provenance_kind is ProvenanceKind.human]
        assert len(machine) == 49 and len(human) == 1
        assert human[0].metadata["box_index"] == 17

    def test_no_converted_row_is_stored_as_the_converting_person(self, db):
        """The person who triggered the conversion did not draw these
        boxes; crediting them would put a historian's name on a machine's
        work, permanently."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc, _block(50, hand_drawn_at=17))
        _invoke(db, document_id=doc.id)

        rows = live_rows_in_order(db, converted_pass_id(artifact.id))
        assert all(row.created_by != "historian" for row in rows)
        assert db.get(SegmentPass, converted_pass_id(artifact.id)).actor is None

    def test_no_version_rows_are_written_at_conversion(self, db):
        """Version rows are PREIMAGES. One written here would leave every
        converted row at version 2 with a snapshot of a state nothing ever
        superseded, and hand the app a stale `expected_version` for a page
        nobody has edited."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc, _block(5))
        _invoke(db, document_id=doc.id)

        rows = live_rows_in_order(db, converted_pass_id(artifact.id))
        assert all(row.version == 1 for row in rows)
        for row in rows:
            assert db.query(SegmentVersion, segment_id=row.id) == []


class TestOnePagePerConversion:
    """`source.store.one-page-per-conversion`, `.no-batch-rewrite`."""

    def test_the_params_model_cannot_name_more_than_one_document(self):
        fields = SegmentConvertAndEditParams.model_fields
        assert "document_id" in fields
        assert not any(name.endswith("_ids") for name in fields), (
            "a list of documents would make a batch rewrite expressible"
        )

    def test_a_second_document_is_untouched(self, db):
        doc_a, doc_b = _make_doc(db, "a.jpg"), _make_doc(db, "b.jpg")
        a1 = _artifact(db, doc_a)
        b1 = _artifact(db, doc_b)
        before_b = db.get(Artifact, b1.id).model_dump(mode="json")

        _invoke(db, document_id=doc_a.id)

        assert db.get(Artifact, b1.id).model_dump(mode="json") == before_b
        assert db.query(SegmentPass, document_id=doc_b.id) == []
        assert db.query(Segment, document_id=doc_b.id) == []


class TestAnArtifactFromAnotherDocumentIsRefused:
    """The permission layer checks `document_id` and `artifact_id` as two
    INDEPENDENT targets, so a mismatched pair arrives allowed."""

    def test_it_is_refused(self, db):
        doc_a, doc_b = _make_doc(db, "a.jpg"), _make_doc(db, "b.jpg")
        _artifact(db, doc_a)
        b1 = _artifact(db, doc_b)
        with pytest.raises(ArtifactNotOnThisDocument):
            _invoke(db, document_id=doc_a.id, artifact_id=b1.id, edit=A_TRIVIAL_EDIT)

    def test_nothing_is_converted_and_nothing_is_marked(self, db):
        doc_a, doc_b = _make_doc(db, "a.jpg"), _make_doc(db, "b.jpg")
        a1 = _artifact(db, doc_a)
        b1 = _artifact(db, doc_b)
        with pytest.raises(ArtifactNotOnThisDocument):
            _invoke(db, document_id=doc_a.id, artifact_id=b1.id, edit=A_TRIVIAL_EDIT)

        assert db.query(Segment, document_id=doc_a.id) == []
        assert db.query(SegmentPass, document_id=doc_a.id) == []
        assert db.get(Artifact, a1.id).geometry_superseded_by_pass_id is None
        assert db.get(Artifact, b1.id).geometry_superseded_by_pass_id is None


class TestAHalfConvertedPageCannotExist:
    def test_a_failure_on_the_third_artifact_rolls_back_the_first_two(self, db, monkeypatch):
        doc = _make_doc(db)
        artifacts = [_artifact(db, doc, _block(3)) for _ in range(3)]

        real_save_many = type(db).save_many
        calls = {"n": 0}

        def exploding(self, objs):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("disk gave out on the third result")
            return real_save_many(self, objs)

        monkeypatch.setattr(type(db), "save_many", exploding)
        with pytest.raises(RuntimeError):
            _invoke(db, document_id=doc.id)
        monkeypatch.undo()

        assert db.query(Segment, document_id=doc.id) == [], "rows survived a rollback"
        assert db.query(SegmentPass, document_id=doc.id) == []
        for artifact in artifacts:
            assert db.get(Artifact, artifact.id).geometry_superseded_by_pass_id is None

    def test_a_failed_conversion_leaves_no_audit_row(self, db, monkeypatch):
        doc = _make_doc(db)
        _artifact(db, doc, _block(2))
        before = len(db.query(ActionAudit))

        def exploding(self, objs):
            raise RuntimeError("no")

        monkeypatch.setattr(type(db), "save_many", exploding)
        with pytest.raises(RuntimeError):
            _invoke(db, document_id=doc.id)
        monkeypatch.undo()
        assert len(db.query(ActionAudit)) == before


class TestTheSecondGuard:
    """The primary key is NO guard: `save`/`save_many` are
    `INSERT ... ON CONFLICT (id) DO UPDATE`, so a second conversion would
    not fail, it would OVERWRITE -- writing a moved box back from the block
    at version 1. A person's edit lost, with nothing raised."""

    def test_a_pass_already_there_stops_the_conversion_even_if_the_marker_is_not(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc, _block(3))
        _invoke(db, document_id=doc.id)

        # Exactly the loser's position: it passed the marker look (the
        # marker is not set for it) but the winner's pass is already there.
        artifact = db.get(Artifact, artifact.id)
        artifact.geometry_superseded_by_pass_id = None
        db.save(artifact)

        with pytest.raises(AlreadyConverted):
            _invoke(db, document_id=doc.id)

    def test_the_winners_moved_box_is_still_moved(self, db):
        """The assertion that matters. An overwrite would put this box back
        where the machine first found it, silently."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc, _block(3))
        _invoke(db, document_id=doc.id)

        moved = live_rows_in_order(db, converted_pass_id(artifact.id))[1]
        moved.anchor = moved.anchor.model_copy(update={"rect": [0.77, 0.77, 0.1, 0.1]})
        moved.version = 2
        db.save(moved)

        artifact = db.get(Artifact, artifact.id)
        artifact.geometry_superseded_by_pass_id = None
        db.save(artifact)
        with pytest.raises(AlreadyConverted):
            _invoke(db, document_id=doc.id)

        still = db.get(Segment, moved.id)
        assert still.anchor.rect == [0.77, 0.77, 0.1, 0.1], "a person's edit was overwritten"
        assert still.version == 2

    def test_two_threads_racing_one_page_convert_it_once(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc, _block(4))

        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        lock = threading.Lock()

        def run():
            barrier.wait()
            try:
                _invoke(db, document_id=doc.id)
                with lock:
                    outcomes.append("converted")
            except Exception as exc:  # noqa: BLE001 -- the TYPE is asserted below
                with lock:
                    outcomes.append(type(exc).__name__)

        threads = [threading.Thread(target=run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        assert not any(t.is_alive() for t in threads), "a racing conversion deadlocked"

        assert outcomes.count("converted") == 1, outcomes
        # The loser's refusal is whichever guard it met -- the marker or
        # the pass -- and either way it did NOT convert a second time.
        assert outcomes.count("converted") + outcomes.count("NothingToConvert") \
            + outcomes.count("AlreadyConverted") == 2, outcomes
        assert len(db.query(SegmentPass, document_id=doc.id)) == 1
        assert len(db.query(Segment, document_id=doc.id)) == 4
        conversions = [
            a for a in db.query(ActionAudit) if a.action_name == "segment.convert_and_edit"
        ]
        assert len(conversions) == 1, "two audit rows for one conversion"


class TestTheAuditRecord:
    def test_one_audit_row_whose_id_is_the_one_the_action_minted(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc, _block(3))
        result = _invoke(db, document_id=doc.id)
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None and audit.action_name == "segment.convert_and_edit"

    def test_the_payload_carries_counts_and_ids_never_twenty_thousand_ids(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc, _block(500))
        result = _invoke(db, document_id=doc.id)
        audit = db.get(ActionAudit, result.audit_id)

        payload = json.dumps(audit.after)
        assert len(payload) < 10_000, f"audit payload is {len(payload)} bytes"
        assert audit.after["segment_count"] == 500
        assert "segment_ids" not in audit.after

    def test_each_kind_is_written_in_one_batch_not_one_row_at_a_time(self, db, monkeypatch):
        """A dense page is 20,000 rows; a per-row loop would be the whole
        cost of the slice.

        TWO batches since slice 8b, not one: the segments, then the reading each
        one's words became. `save_many` writes a single table per call, so they
        cannot share a batch — and what this test is actually about is that
        neither is written a row at a time. Asserting a batch COUNT would pass
        the day someone loops per row in a second place; asserting that every
        batch is a full page is the property."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc, _block(40))

        batches: list[int] = []
        real = type(db).save_many

        def counting(self, objs):
            objs = list(objs)
            batches.append(len(objs))
            return real(self, objs)

        monkeypatch.setattr(type(db), "save_many", counting)
        _invoke(db, document_id=doc.id)
        monkeypatch.undo()

        # 40 segments and 40 readings, each in ONE call. No batch of 1, which is
        # what a per-row loop would look like however many calls it made.
        assert batches == [40, 40], batches
        assert all(size == 40 for size in batches), batches


class TestUndo:
    def test_a_conversion_that_carried_no_edit_has_no_inverse(self, db):
        """`None` is the undo route's own word for "this has no inverse",
        and it answers it with a clean 409. Raising here instead made the
        history list a conversion as undoable and then 500 when somebody
        pressed it (#4924 review, FIX FIRST 4)."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        result = _invoke(db, document_id=doc.id)
        audit = db.get(ActionAudit, result.audit_id)
        reg = registry.get("segment.convert_and_edit")
        assert reg.invert(audit.before, audit.after, _ctx()) is None

    def test_the_action_declares_the_redo_rule_it_needs(self, db):
        """#4957: replaying the params would re-run the conversion branch,
        and the edit it carries (step 5) can mint a row."""
        reg = registry.get("segment.convert_and_edit")
        assert reg.redo_via_own_invert is True
        assert reg.undoable is True and reg.atomic is True


class TestSliceSixRepointsNothing:
    """RULED 2026-09-20: the matcher RUNS and every match is REPORTED; not
    one of the four anchor-carrying kinds is written to.

    None of them has a lasting segment reference to write into.
    `KnowledgeClaim.source_segment_id` looks like one and is not: it
    predates the source model, is client-supplied, is published in the API
    contract, has no engine producer, and its older meaning is an entry in
    a segmentation artifact's `data["segments"]`. Putting real row ids
    there would merge two meanings in one published column in somebody's
    real research library.
    """

    @staticmethod
    def _anchored(db, doc, rect):
        """One record of every kind that rests on a place, all on the same
        rectangle, so one converted box matches all four."""
        from fichero_server.models import ContentRepresentation, ContentRepresentationKind
        from fichero_server.models.anchors import SourceAnchor
        from fichero_server.models.knowledge import (
            Annotation, AnnotationKind, KnowledgeClaim, SourceSupport,
        )

        anchor = SourceAnchor(document_id=doc.id, rect=list(rect))
        # `SourceSupport` is NOT a row: it has no `id` and no table, and
        # lives in `source_supports` on a claim (and on an entity). It is
        # reported as `<claim id>#<position>`, the only honest way to name
        # something with no id of its own.
        support = SourceSupport(source_document_id=doc.id, source_anchor=anchor)
        claim = KnowledgeClaim(
            text="the alcalde signed here", source_document_id=doc.id,
            source_anchor=anchor, source_supports=[support],
        )
        reading = ContentRepresentation(
            document_id=doc.id, kind=ContentRepresentationKind.transcription,
            content="a reading of the first line", source_anchor=anchor,
        )
        mark = Annotation(
            kind=AnnotationKind.highlight, document_id=doc.id, anchor=anchor,
        )
        for row in (claim, reading, mark):
            db.save(row)
        return claim, reading, mark

    def test_all_four_anchored_kinds_are_found_and_reported(self, db):
        doc = _make_doc(db)
        block = _block(3)
        artifact = _artifact(db, doc, block)
        self._anchored(db, doc, block.boxes[0].bbox)

        result = _invoke(db, document_id=doc.id)
        reported = result.result["not_repointed"]
        assert result.result["not_repointed_count"] == 4
        assert {e["kind"] for e in reported} == {
            "claim", "source_support", "reading", "annotation"
        }
        expected = converted_segment_id(artifact.id, 0)
        assert all(e["segment_id"] == expected for e in reported)
        assert all("no lasting segment reference" in e["reason"] for e in reported)
        # The embedded one is named by its parent and its position.
        support_entry = next(e for e in reported if e["kind"] == "source_support")
        assert support_entry["id"].endswith("#0")

    def test_a_support_on_an_entity_is_a_known_gap_not_a_silent_skip(self, db):
        """Walking them means scanning every entity in the library on every
        first edit, because an entity is scoped by a LIST column. Pinned so
        the gap is a decision on record, not something a later reader has
        to rediscover."""
        from fichero_server.api.routes.document.segment_conversion import (
            SOURCE_SUPPORT_PARENTS_WALKED,
        )

        assert SOURCE_SUPPORT_PARENTS_WALKED == ("claim",)

    def test_nothing_is_repointed(self, db):
        doc = _make_doc(db)
        block = _block(3)
        artifact = _artifact(db, doc, block)
        self._anchored(db, doc, block.boxes[0].bbox)

        result = _invoke(db, document_id=doc.id)
        assert result.result["repointed"] == []

    def test_no_record_is_written_to_at_all(self, db):
        """The assertion that matters: every one of the four rows is
        byte-equal after the conversion that matched it."""
        doc = _make_doc(db)
        block = _block(3)
        artifact = _artifact(db, doc, block)
        records = self._anchored(db, doc, block.boxes[0].bbox)
        before = [r.model_dump(mode="json") for r in records]
        # The embedded support rides inside the claim's dump, so comparing
        # the claim byte for byte covers it too.

        _invoke(db, document_id=doc.id)

        for original, was in zip(records, before, strict=True):
            reread = db.get(type(original), original.id)
            assert reread is not None
            assert reread.model_dump(mode="json") == was, (
                f"{type(original).__name__} was written to"
            )

    def test_the_legacy_claim_column_is_left_exactly_as_it_was(self, db):
        """`source_segment_id` is a published column with an older meaning.
        Pinned on its own because it is the one that LOOKS writable."""
        from fichero_server.models.knowledge import KnowledgeClaim

        doc = _make_doc(db)
        block = _block(3)
        artifact = _artifact(db, doc, block)
        claim, *_ = self._anchored(db, doc, block.boxes[0].bbox)
        assert claim.source_segment_id is None

        _invoke(db, document_id=doc.id)
        assert db.get(KnowledgeClaim, claim.id).source_segment_id is None

    def test_a_pre_existing_legacy_value_is_not_overwritten(self, db):
        """A library where something once set it keeps what it had."""
        from fichero_server.models.anchors import SourceAnchor
        from fichero_server.models.knowledge import KnowledgeClaim

        doc = _make_doc(db)
        block = _block(3)
        artifact = _artifact(db, doc, block)
        claim = KnowledgeClaim(
            text="older data", source_document_id=doc.id,
            source_anchor=SourceAnchor(document_id=doc.id, rect=list(block.boxes[0].bbox)),
            source_segment_id="an-old-segmentation-entry",
        )
        db.save(claim)

        _invoke(db, document_id=doc.id)
        assert db.get(KnowledgeClaim, claim.id).source_segment_id == "an-old-segmentation-entry"

    def test_a_record_that_only_nearly_matches_is_not_reported(self, db):
        """Never by overlap or nearness: a record that nearly matches a box
        is a record about something else, and reporting it as a candidate
        would invite somebody to attach it later."""
        doc = _make_doc(db)
        block = _block(3)
        artifact = _artifact(db, doc, block)
        nearly = list(block.boxes[0].bbox)
        nearly[0] += 0.01
        self._anchored(db, doc, nearly)

        result = _invoke(db, document_id=doc.id)
        assert result.result["not_repointed"] == []
        assert result.result["not_repointed_count"] == 0

    def test_a_record_on_another_document_is_not_reported(self, db):
        doc = _make_doc(db, "a.jpg")
        other = _make_doc(db, "b.jpg")
        block = _block(3)
        artifact = _artifact(db, doc, block)
        self._anchored(db, other, block.boxes[0].bbox)

        result = _invoke(db, document_id=doc.id)
        assert result.result["not_repointed_count"] == 0

    def test_a_page_with_many_matches_reports_every_one_to_the_caller(self, db):
        """The full list goes to the CALLER; only the count goes in the
        audit chain (#4924 review, FIX FIRST 3). The chain-side assertion
        lives in `test_conversion_undo_and_refusals.py`."""
        from fichero_server.models import ContentRepresentation, ContentRepresentationKind
        from fichero_server.models.anchors import SourceAnchor

        doc = _make_doc(db)
        block = _block(3)
        artifact = _artifact(db, doc, block)
        for i in range(27):
            db.save(ContentRepresentation(
                document_id=doc.id, kind=ContentRepresentationKind.transcription,
                content=f"reading {i}",
                source_anchor=SourceAnchor(document_id=doc.id, rect=list(block.boxes[0].bbox)),
            ))

        result = _invoke(db, document_id=doc.id)
        assert result.result["not_repointed_count"] == 27
        assert len(result.result["not_repointed"]) == 27


class TestWhatDeferringRepointingActuallyCosts:
    """The evidence for the spec writer's ruling, written down as tests.

    Slice 6 re-points nothing, so every `SourceAnchor.rect` keeps the
    number it was written with. What a historian then sees depends on HOW
    the record finds its pixels, and the three ways differ.

    CORRECTED after the author's second look: the link between a mark and
    its line is NOT lost when the box moves. Matching against the LIVE rows
    fails, yes -- but THE KEPT BLOCK'S BOXES NEVER MOVE. So "the rectangle
    this mark was made from" can still be found in the block, its POSITION
    there gives the repeatable segment id, and that resolves to the line
    wherever the line is now, at any later time. The conversion-time match
    list is a convenience, not the only evidence -- one more reason it
    belongs in the result and not in the audit row.

    That resolver is #4990 (slice 6b) and is NOT built here. These tests
    pin the facts it will rest on.
    """

    def test_matching_against_live_rows_fails_after_a_move(self, db):
        """True, and the reason the conversion-time list is only a
        convenience. `_anchor_matches_segment` is exact to 1e-6 -- rightly,
        because a near match is a record about something else -- so once
        the row has moved, the record matches no LIVE row at all."""
        from fichero_server.api.routes.document.segment_conversion import repointing_report
        from fichero_server.models.anchors import SourceAnchor
        from fichero_server.models.knowledge import KnowledgeClaim

        doc = _make_doc(db)
        block = _block(3)
        artifact = _artifact(db, doc, block)
        db.save(KnowledgeClaim(
            text="the alcalde signed here", source_document_id=doc.id,
            source_anchor=SourceAnchor(document_id=doc.id, rect=list(block.boxes[0].bbox)),
        ))
        _invoke(db, document_id=doc.id)

        rows = live_rows_in_order(db, converted_pass_id(artifact.id))
        assert repointing_report(db, rows)["not_repointed_count"] == 1

        moved = rows[0]
        moved.anchor = moved.anchor.model_copy(update={"rect": [0.6, 0.6, 0.2, 0.05]})
        db.save(moved)

        rows_after = live_rows_in_order(db, converted_pass_id(artifact.id))
        assert repointing_report(db, rows_after)["not_repointed_count"] == 0

    def test_matching_through_the_kept_block_still_finds_the_line(self, db):
        """THE CORRECTION, and the whole premise of #4990.

        The kept block is the record of what the machine produced and is
        never written again. So a rectangle recorded before anybody moved
        anything is still in it, at the same POSITION -- and a position
        plus the artifact id is exactly what `converted_segment_id` takes.
        The mark finds its line wherever the line has since gone.

        Written here, without the resolver, to prove the pieces exist.
        """
        from fichero_server.models.anchors import SourceAnchor
        from fichero_server.models.knowledge import KnowledgeClaim

        doc = _make_doc(db)
        block = _block(3)
        artifact = _artifact(db, doc, block)
        remembered_rect = list(block.boxes[1].bbox)
        db.save(KnowledgeClaim(
            text="the second line", source_document_id=doc.id,
            source_anchor=SourceAnchor(document_id=doc.id, rect=remembered_rect),
        ))
        _invoke(db, document_id=doc.id)

        row = live_rows_in_order(db, converted_pass_id(artifact.id))[1]
        row.anchor = row.anchor.model_copy(update={"rect": [0.6, 0.6, 0.2, 0.05]})
        db.save(row)

        # The resolver #4990 will be, in three lines.
        kept = db.get(Artifact, artifact.id).ocr_geometry
        position = next(
            i for i, box in enumerate(kept.boxes)
            if all(abs(a - b) <= 1e-6 for a, b in zip(box.bbox, remembered_rect))
        )
        resolved = db.get(Segment, converted_segment_id(artifact.id, position))

        assert resolved is not None
        assert resolved.id == row.id, "the mark found its line"
        assert resolved.anchor.rect == [0.6, 0.6, 0.2, 0.05], "and the line has moved"

    def test_the_kept_block_is_byte_equal_after_every_door_is_tried(self, db):
        """#4990 rests on the block never changing. Every writer that could
        touch it is refused or keeps it: `regions_edit`, `artifact.delete`,
        `artifact.restore` and the bulk document restore.
        """
        from fichero_server.api.routes.document.documents import restore_documents_impl
        from fichero_server.api.routes.document.segment_conversion import (
            restored_artifact_row,
        )

        doc = _make_doc(db)
        block = _block(3)
        artifact = _artifact(db, doc, block)
        snapshot = db.get(Artifact, artifact.id).model_dump(mode="json")
        _invoke(db, document_id=doc.id)
        kept = db.get(Artifact, artifact.id).model_dump(mode="json")["ocr_geometry"]

        with pytest.raises(Exception):
            _invoke_action(db, "artifact.regions_edit", {
                "artifact_id": artifact.id,
                "edit": {"op": "move", "indices": [0], "bbox": [0.9, 0.9, 0.05, 0.05]},
            })
        with pytest.raises(Exception):
            _invoke_action(db, "artifact.delete", {"artifact_id": artifact.id})

        # A snapshot with DIFFERENT boxes, through both restore paths.
        forged = dict(snapshot)
        forged["ocr_geometry"] = dict(snapshot["ocr_geometry"])
        forged["ocr_geometry"]["boxes"] = snapshot["ocr_geometry"]["boxes"][:1]
        with pytest.raises(Exception):
            restored_artifact_row(db, forged, refuse_different_boxes=True)
        restore_documents_impl(db, doc_ids=[], documents=[], artifacts=[forged])

        assert db.get(Artifact, artifact.id).model_dump(mode="json")["ocr_geometry"] == kept

    def test_a_record_that_finds_its_pixels_by_char_span_follows_the_move(self, db, client):
        """The half that is FINE. The app resolves a char span against the
        boxes it gets from `GET /api/artifacts/{id}`, and that response is
        `live_geometry` -- so a span-anchored claim or annotation lands on
        the box where the historian put it.
        """
        doc = _make_doc(db)
        block = _block(3)
        artifact = _artifact(db, doc, block)
        _invoke(db, document_id=doc.id)

        moved = live_rows_in_order(db, converted_pass_id(artifact.id))[0]
        moved.anchor = moved.anchor.model_copy(update={"rect": [0.6, 0.6, 0.2, 0.05]})
        db.save(moved)

        r = client.get(f"/api/artifacts/{artifact.id}")
        assert r.status_code == 200, r.text
        boxes = r.json()["ocr_geometry"]["boxes"]
        assert boxes[0]["bbox"] == [0.6, 0.6, 0.2, 0.05]
        assert boxes[0]["text"] == "w0", "and it must still carry its words"

    def test_a_record_that_draws_from_its_stored_rect_does_not_follow(self, db):
        """The half that is NOT fine TODAY, and what #4990 is for.

        Every rectangle an `Annotation` draws on a page image comes from
        its stored `anchor.rect` (`AnnotationService.regionRect`), and a
        claim carrying both a rect and a span draws the rect on a PDF. So
        until the resolver exists, a highlight, a star or a note stays
        where the box used to be.
        """
        from fichero_server.models.anchors import SourceAnchor
        from fichero_server.models.knowledge import Annotation, AnnotationKind

        doc = _make_doc(db)
        block = _block(3)
        artifact = _artifact(db, doc, block)
        original_rect = list(block.boxes[0].bbox)
        mark = Annotation(
            kind=AnnotationKind.highlight, document_id=doc.id,
            anchor=SourceAnchor(document_id=doc.id, rect=original_rect),
        )
        db.save(mark)
        _invoke(db, document_id=doc.id)

        moved = live_rows_in_order(db, converted_pass_id(artifact.id))[0]
        moved.anchor = moved.anchor.model_copy(update={"rect": [0.6, 0.6, 0.2, 0.05]})
        db.save(moved)

        assert db.get(Annotation, mark.id).anchor.rect == original_rect
