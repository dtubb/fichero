"""One page holds several languages and scripts at once, end to end (#4938).

`source.lang.many-per-page`. The storage half is pinned in
``tests/unit/models/test_segment_language_and_script.py``: two regions of one
page can hold two languages. This file asserts the half that makes the behavior
usable — that the READ SEAM carries them, so the app receives three answers for
one page instead of the one answer a page-level field could give.

Everything goes through the real route and the real conversion, not through
``SegmentRead`` constructed by hand: a field on the model that the builder never
fills is exactly the failure this test exists to catch.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, Document, DocType, FileType, Segment, Status
from fichero_server.models.source_declarations import UnknownScript, declare_script

pytestmark = pytest.mark.source_model

#: A Spanish entry, an Arabic gloss beside it, and a line in a hand no registry
#: has. The point of the fixture is that no single page-level answer is right
#: for all three.
LINES = ("en el nombre de dios", "بسم الله", "the clerk's own hand")


def _page(db) -> tuple[Document, Artifact]:
    doc = Document(
        name="mixed.jpg", doc_type=DocType.file, file_type=FileType.image,
        path="/path/mixed.jpg", status=Status.completed,
    )
    db.save(doc)
    artifact = Artifact(
        document_id=doc.id, artifact_type="transcription", provider="qwen", model="qwen-vl",
        content=" ".join(LINES),
        ocr_geometry=OCRGeometryResult(
            provider="qwen", text=" ".join(LINES),
            boxes=[
                OCRGeometryBox(
                    text=line, bbox=[0.1, 0.1 + index * 0.2, 0.4, 0.05], level="line",
                    confidence=0.8,
                )
                for index, line in enumerate(LINES)
            ],
        ),
    )
    db.save(artifact)
    return doc, artifact


def _convert(client, artifact_id: str) -> None:
    """Convert the page the way the app does: its first edit."""
    response = client.put(
        f"/api/artifacts/{artifact_id}/regions",
        json={"op": "move", "indices": [0], "bbox": [0.11, 0.1, 0.4, 0.05]},
    )
    assert response.status_code == 200, response.text


def _rows_in_order(db, doc_id: str) -> list[Segment]:
    rows = [row for row in db.query(Segment, document_id=doc_id) if row.deleted_at is None]
    return sorted(rows, key=lambda row: (row.anchor.rect or [0.0, 0.0])[1])


def _read(client, doc_id: str) -> list[dict]:
    response = client.get(f"/api/segments/document/{doc_id}")
    assert response.status_code == 200, response.text
    return response.json()["segments"]


class TestThePageComesBackWithSeveralAnswers:
    def test_three_segments_of_one_page_report_three_scripts(self, db, client):
        doc, artifact = _page(db)
        _convert(client, artifact.id)
        declare_script(db, "Qaaa", "The clerk's hand")

        rows = _rows_in_order(db, doc.id)
        assert len(rows) == len(LINES), "the page did not convert into one row per line"
        for row, (language, script) in zip(
            rows, [("es", "Latn"), ("ar", "Arab"), ("es", "Qaaa")]
        ):
            row.language = language
            row.script = script
            db.save(row)

        seam = {item["id"]: item for item in _read(client, doc.id)}
        answers = [(seam[row.id]["language"], seam[row.id]["script"]) for row in rows]

        assert answers == [("es", "Latn"), ("ar", "Arab"), ("es", "Qaaa")]
        # The behavior, stated as the test: three scripts on ONE page, so no
        # page-level field could have carried this without being wrong twice.
        assert len({script for _lang, script in answers}) == 3
        assert len({item["document_id"] for item in seam.values()}) == 1

    def test_a_declared_script_reaches_the_app_as_its_code(self, db, client):
        """The project's own script is not special-cased anywhere in the seam:
        it travels as a code like `Latn` does, and what it MEANS is a separate
        lookup (`script_display_name`). A seam that resolved names here would
        make a declaration's absence look like a missing script."""
        doc, artifact = _page(db)
        _convert(client, artifact.id)
        rows = _rows_in_order(db, doc.id)
        rows[0].script = "Qabx"  # deliberately NOT declared
        db.save(rows[0])

        seam = {item["id"]: item for item in _read(client, doc.id)}
        assert seam[rows[0].id]["script"] == "Qabx"


class TestSayingNothingStaysPossible:
    def test_a_segment_that_states_nothing_reads_as_null_not_as_unknown(self, db, client):
        """`unknown-is-not-unexamined` at the seam: `None` falls through the
        cascade, and a seam that substituted a default would make every region
        look examined."""
        doc, artifact = _page(db)
        _convert(client, artifact.id)

        for item in _read(client, doc.id):
            assert item["language"] is None
            assert item["script"] is None

    def test_a_provisional_segment_reports_null_for_both(self, db, client):
        """Read BEFORE conversion, so the rows are boxes inside the artifact
        blob. There is nowhere in that blob for a language to have been stored,
        and inventing one from the artifact's provider would be a guess."""
        doc, artifact = _page(db)

        items = _read(client, doc.id)
        assert items, "the provisional read returned nothing"
        assert all(item["provisional"] for item in items)
        for item in items:
            assert item["language"] is None
            assert item["script"] is None

    def test_conversion_does_not_drop_a_value_the_provisional_read_had(self, db, client):
        """The field-parity rule this seam already follows for
        `source_artifact_id`: a converted read must not report less than the
        provisional one did. Both are `None` here, which is the parity — stated
        as a test so a later writer of provisional languages has to keep it."""
        doc, artifact = _page(db)
        before = {item["box_index"]: item for item in _read(client, doc.id)}
        _convert(client, artifact.id)
        after = _read(client, doc.id)

        assert len(after) == len(before)
        for item in after:
            assert item["language"] is None
            assert item["script"] is None


# ---------------------------------------------------------------------------
# The write path (#4938). Until this existed the fields could not be SET, so
# `many-per-page` could not be true end to end however faithful the seam was.
# ---------------------------------------------------------------------------


def _set_facts(db, segment, *, actor: str = "historian", **facts):
    from fichero_server.actions.registry import ActionContext, registry

    return registry.invoke(
        db,
        "segment.update",
        {"segment_id": segment.id, "expected_version": segment.version, **facts},
        ActionContext(actor=actor, is_bootstrap=True),
    )


class TestTheFactsCanBeSet:
    def test_a_person_sets_all_three_facts_on_one_region(self, db, client):
        from fichero_server.llm.language_policy import LEVEL_SEGMENT, SOURCE_USER

        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]

        _set_facts(db, row, language="es", script="Latn", direction="ltr")

        stored = db.get(Segment, row.id)
        assert (stored.language, stored.script, stored.direction) == ("es", "Latn", "ltr")
        # Provenance is the ENGINE's, built from ctx (#4868/#4869): a person's
        # judgement recorded as a person's.
        for meta in (stored.language_meta, stored.script_meta, stored.direction_meta):
            assert meta["source"] == SOURCE_USER
            assert meta["level"] == LEVEL_SEGMENT
            assert "a person" in meta["basis"]

    def test_a_runs_determination_is_not_recorded_as_a_persons(self, db, client):
        """The defect #4868/#4869 exists for: a machine's answer stored as
        `user` is indistinguishable from a curator's, forever."""
        from fichero_server.llm.language_policy import SOURCE_DETECTED, SOURCE_USER

        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]

        from fichero_server.actions.registry import ActionContext, registry

        registry.invoke(
            db,
            "segment.update",
            {"segment_id": row.id, "expected_version": row.version, "language": "es"},
            ActionContext(actor="runner", run_id="run-1", is_bootstrap=True),
        )

        stored = db.get(Segment, row.id)
        assert stored.language_meta["source"] == SOURCE_DETECTED
        assert stored.language_meta["source"] != SOURCE_USER
        assert "this run" in stored.language_meta["basis"]

    def test_a_caller_cannot_supply_its_own_provenance(self, db, client):
        """`language_meta` is not a parameter. A caller that could send one could
        claim a person set what a model guessed."""
        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]

        with pytest.raises(Exception) as raised:
            _set_facts(db, row, language="es", language_meta={"source": "user"})
        assert "language_meta" in str(raised.value) or "extra" in str(raised.value).lower()

    def test_setting_nothing_leaves_every_fact_alone(self, db, client):
        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]
        _set_facts(db, row, language="es")

        reread = db.get(Segment, row.id)
        _set_facts(db, reread, is_furniture=True)

        stored = db.get(Segment, row.id)
        assert stored.language == "es", "an unrelated update cleared a fact"
        assert stored.is_furniture is True


class TestTheWritePathRefusesWhatTheReadPathWouldNotUnderstand:
    def test_an_undeclared_private_use_script_is_refused(self, db, client):
        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]

        with pytest.raises(HTTPException) as raised:
            _set_facts(db, row, script="Qabv")
        assert raised.value.status_code == 422
        assert "declare" in str(raised.value.detail)
        # And nothing was written: a refused write is not a partial write.
        assert db.get(Segment, row.id).script is None

    def test_the_same_code_is_accepted_once_declared(self, db, client):
        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]
        declare_script(db, "Qabv", "The clerk's hand")

        _set_facts(db, row, script="Qabv")

        assert db.get(Segment, row.id).script == "Qabv"

    def test_a_direction_outside_the_six_is_refused(self, db, client):
        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]

        with pytest.raises(HTTPException) as raised:
            _set_facts(db, row, direction="left-to-right")
        assert raised.value.status_code == 422
        assert "follows-baseline" in str(raised.value.detail)

    def test_the_write_path_validates_the_same_way_the_reading_one_does(self, db, client):
        """One validated path per fact. The sibling-defect shape is a fix that
        lands on one caller and not the others, so this asserts the two callers
        refuse the same value rather than trusting that they do."""
        from fichero_server.actions.registry import ActionContext, registry

        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]

        with pytest.raises(HTTPException):
            _set_facts(db, row, script="Qabu")
        with pytest.raises(UnknownScript):
            registry.invoke(
                db,
                "representation.create",
                {
                    "document_id": doc.id, "segment_id": row.id,
                    "kind": "transcription", "content": "x", "script": "Qabu",
                },
                ActionContext(actor="historian", is_bootstrap=True),
            )


class TestUndoRestoresAFact:
    def test_undoing_a_language_change_restores_the_previous_one(self, db, client):
        """The reason the three facts had to go into `SegmentVersion`: a field the
        update can change and the preimage does not carry is a field undo leaves
        at its new value, which is worse than not being editable at all."""
        from fichero_server.actions.registry import ActionContext, registry

        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]

        _set_facts(db, row, language="es", script="Latn")
        after_first = db.get(Segment, row.id)
        _set_facts(db, after_first, language="la")
        after_second = db.get(Segment, row.id)
        assert after_second.language == "la"

        registry.invoke(
            db,
            "segment.restore_version",
            {
                "segment_id": row.id,
                "version": after_second.version - 1,
                "expected_version": after_second.version,
            },
            ActionContext(actor="historian", is_bootstrap=True),
        )

        restored = db.get(Segment, row.id)
        assert restored.language == "es", "undo left the new value in place"
        assert restored.script == "Latn", "undo lost a fact it never changed"


class TestManyPerPageEndToEnd:
    def test_three_regions_are_SET_to_three_scripts_and_READ_BACK_as_three(self, db, client):
        """The behaviour, whole: recorded through the real action, read through
        the real route. Neither half proves it alone — the seam could carry three
        answers nothing can produce, and the writer could store three nothing can
        see."""
        doc, artifact = _page(db)
        _convert(client, artifact.id)
        declare_script(db, "Qabt", "The clerk's hand")

        for row, (language, script) in zip(
            _rows_in_order(db, doc.id), [("es", "Latn"), ("ar", "Arab"), ("es", "Qabt")]
        ):
            _set_facts(db, row, language=language, script=script)

        seam = _read(client, doc.id)
        answers = sorted((item["language"], item["script"]) for item in seam)

        assert answers == sorted([("es", "Latn"), ("ar", "Arab"), ("es", "Qabt")])
        assert len({script for _l, script in answers}) == 3


class TestAFactCanBeClearedNotOnlyCorrected:
    """`segment.facts_clear` — the segment-level half of `source_setting.clear`.

    Correcting a value and withdrawing it are different acts. Without this, a
    curator who stated a language they should never have stated could only undo
    the change (which needs the change to be the most recent one) or set a
    different wrong value.
    """

    def _clear(self, db, segment, *keys):
        from fichero_server.actions.registry import ActionContext, registry

        return registry.invoke(
            db,
            "segment.facts_clear",
            {
                "segment_id": segment.id,
                "expected_version": segment.version,
                "keys": list(keys),
            },
            ActionContext(actor="historian", is_bootstrap=True),
        )

    def test_clearing_returns_a_fact_to_never_determined(self, db, client):
        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]
        _set_facts(db, row, language="es", script="Latn")

        self._clear(db, db.get(Segment, row.id), "language")

        stored = db.get(Segment, row.id)
        assert stored.language is None
        # The meta goes with it: provenance for a fact that no longer exists
        # would say a person determined something that is not there.
        assert stored.language_meta is None
        # And only what was named is cleared.
        assert stored.script == "Latn"
        assert stored.script_meta is not None

    def test_a_cleared_fact_falls_through_the_cascade_again(self, db, client):
        """The behavioural difference between cleared and examined-and-unknown:
        cleared FALLS THROUGH to the next level, where an unknown would stop the
        walk. That is `unknown-is-not-unexamined` as a write."""
        from fichero_server.llm.language_policy import LEVEL_DOCUMENT, resolve_language
        from fichero_server.models import Document

        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]
        _set_facts(db, row, language="Latin")

        document = db.get(Document, doc.id)
        document.language = "Spanish"
        db.save(document)

        before = resolve_language(segment=db.get(Segment, row.id), document=document, detect=False)
        assert before.language == "Latin"

        self._clear(db, db.get(Segment, row.id), "language")

        after = resolve_language(segment=db.get(Segment, row.id), document=document, detect=False)
        assert after.language == "Spanish"
        assert after.level == LEVEL_DOCUMENT

    def test_clearing_is_undoable_like_any_other_change(self, db, client):
        from fichero_server.actions.registry import ActionContext, registry

        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]
        _set_facts(db, row, language="es")

        self._clear(db, db.get(Segment, row.id), "language")
        after_clear = db.get(Segment, row.id)
        assert after_clear.language is None

        registry.invoke(
            db,
            "segment.restore_version",
            {
                "segment_id": row.id,
                "version": after_clear.version - 1,
                "expected_version": after_clear.version,
            },
            ActionContext(actor="historian", is_bootstrap=True),
        )

        restored = db.get(Segment, row.id)
        assert restored.language == "es"
        assert restored.language_meta is not None, "undo restored the value but not its provenance"

    def test_clearing_several_facts_at_once(self, db, client):
        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]
        _set_facts(db, row, language="es", script="Latn", direction="ltr")

        self._clear(db, db.get(Segment, row.id), "language", "script", "direction")

        stored = db.get(Segment, row.id)
        assert (stored.language, stored.script, stored.direction) == (None, None, None)

    def test_an_unnamed_fact_is_refused_and_the_list_is_named(self, db, client):
        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]

        with pytest.raises(HTTPException) as raised:
            self._clear(db, row, "lang")
        assert raised.value.status_code == 422
        assert "direction" in str(raised.value.detail)

    def test_encoding_is_refused_with_the_reason_rather_than_the_list_alone(self, db, client):
        """The one a caller WILL try: encoding is the third fact of
        `three-facts`, and it is not on a segment at all. Being told only "not a
        fact a segment carries" would leave them hunting."""
        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]

        with pytest.raises(HTTPException) as raised:
            self._clear(db, row, "encoding")
        assert "script row" in str(raised.value.detail)

    def test_clearing_nothing_is_refused_rather_than_a_no_op_audit_row(self, db, client):
        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]

        with pytest.raises(HTTPException) as raised:
            self._clear(db, row)
        assert raised.value.status_code == 422

    def test_a_stale_clear_is_refused(self, db, client):
        doc, artifact = _page(db)
        _convert(client, artifact.id)
        row = _rows_in_order(db, doc.id)[0]
        _set_facts(db, row, language="es")  # bumps the version past `row`'s

        with pytest.raises(HTTPException) as raised:
            self._clear(db, row, "language")
        assert raised.value.status_code == 409
