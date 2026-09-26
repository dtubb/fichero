"""Slice 6 (#4924) -- what the READ SEAM does once a page is converted.

The rows are written BY HAND here, not through the conversion action. That
is deliberate and it is the point: the seam's behaviour has to be right
before anything converts a real page, and a test that went through the
action could not tell a seam bug from a conversion bug.

Behaviours pinned:
* `source.one-store` -- a converted page's boxes come back ONCE, and the
  caller cannot tell which store they came from.
* `source.seam.read-either-store` -- the marker, and only the marker,
  decides; a dangling marker refuses rather than serving a stale page.
* The text fill, and its #4958 refusal.
"""

from __future__ import annotations

import pytest

from fichero_server.core.timeutil import utc_now
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType, Status
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import (
    SegmentPass,
    legacy_pass_id,
    rows_from_reads,
    segments_from_result,
)

pytestmark = pytest.mark.source_model


def _make_doc(db, name: str = "page.jpg") -> Document:
    doc = Document(
        name=name, doc_type=DocType.file, file_type=FileType.image,
        path=f"/path/{name}", status=Status.completed,
    )
    db.save(doc)
    return doc


def _block() -> OCRGeometryResult:
    return OCRGeometryResult(
        provider="qwen",
        model="qwen-vl-max",
        text="Primero. Segundo. Tercero.",
        boxes=[
            OCRGeometryBox(
                text="Primero.", bbox=[0.1, 0.1, 0.2, 0.05], level="line",
                char_start=0, char_end=8, page_index=0,
            ),
            OCRGeometryBox(
                text="Segundo.", bbox=[0.1, 0.2, 0.2, 0.05], level="line",
                char_start=9, char_end=17, page_index=1,
            ),
            OCRGeometryBox(
                text="Tercero.", bbox=[0.1, 0.3, 0.2, 0.05], level="line",
                char_start=18, char_end=26, page_index=1,
            ),
        ],
    )


def _artifact(db, doc, block=None) -> Artifact:
    artifact = Artifact(
        document_id=doc.id, artifact_type="transcription",
        provider="qwen", model="qwen-vl-max",
        ocr_geometry=block if block is not None else _block(),
    )
    db.save(artifact)
    return artifact


def _convert_by_hand(db, doc, artifact) -> SegmentPass:
    pass_row, rows = rows_from_reads(*segments_from_result(
        document_id=doc.id, artifact_id=artifact.id, result=artifact.ocr_geometry,
        provider=artifact.provider, model=artifact.model, run_id=artifact.run_id,
        created_at=artifact.created_at, artifact_type=artifact.artifact_type,
    ))
    db.save(pass_row)
    for row in rows:
        db.save(row)
    artifact.geometry_superseded_by_pass_id = pass_row.id
    db.save(artifact)
    return pass_row


def _read(client, doc_id: str, **params):
    r = client.get(f"/api/segments/document/{doc_id}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


class TestAConvertedPageComesBackOnce:
    def test_the_boxes_are_not_returned_twice(self, client, db):
        """Without the seam's one `if`, a converted page answers with every
        box twice -- once as a real segment and once as the provisional one
        it replaced. This is the first test of the slice."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        before = _read(client, doc.id)
        assert len(before["segments"]) == 3
        assert len(before["passes"]) == 1

        pass_row = _convert_by_hand(db, doc, artifact)
        after = _read(client, doc.id)
        assert len(after["segments"]) == 3, "the page came back twice"
        assert len(after["passes"]) == 1
        assert after["passes"][0]["id"] == pass_row.id
        assert after["passes"][0]["provisional"] is False

    def test_the_provisional_pass_id_is_gone_from_the_answer(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert_by_hand(db, doc, artifact)
        body = _read(client, doc.id)
        assert legacy_pass_id(artifact.id) not in [p["id"] for p in body["passes"]]
        assert all(s["provisional"] is False for s in body["segments"])

    def test_an_unconverted_artifact_beside_a_converted_one_still_reads(self, db, client):
        """Per artifact, not per document: a machine run after conversion
        writes a block, shows beside the rows, and is converted by the next
        edit."""
        doc = _make_doc(db)
        converted = _artifact(db, doc)
        _convert_by_hand(db, doc, converted)
        _artifact(db, doc)  # a later run, still provisional

        body = _read(client, doc.id)
        assert len(body["passes"]) == 2
        assert sorted(p["provisional"] for p in body["passes"]) == [False, True]
        assert len(body["segments"]) == 6


class TestConversionChangesNothingYouCanSeeThroughTheSeam:
    """`source.store.conversion-changes-nothing-seen`, through the real
    route. Run WITHOUT `area`: the seam's legacy branch ignores that filter
    while the real-row branch applies it, which is a pre-existing gap filed
    as #4985 and would confound this comparison."""

    def test_the_response_is_the_same_but_for_id_pass_id_and_provisional(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        before = _read(client, doc.id)
        _convert_by_hand(db, doc, artifact)
        after = _read(client, doc.id)

        assert len(before["segments"]) == len(after["segments"])
        for b, a in zip(before["segments"], after["segments"], strict=True):
            for field in ("id", "pass_id", "provisional"):
                b.pop(field), a.pop(field)
            added_index = a["metadata"].pop("box_index")
            added_page = a["metadata"].pop("page_index", None)
            assert added_index == b["box_index"]
            assert added_page == b["page_index"]
            assert a == b

    def test_every_box_keeps_its_words_through_the_seam(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        before = [s["text"] for s in _read(client, doc.id)["segments"]]
        _convert_by_hand(db, doc, artifact)
        after = [s["text"] for s in _read(client, doc.id)["segments"]]
        assert after == before == ["Primero.", "Segundo.", "Tercero."]

    def test_the_passs_text_survives_so_char_spans_still_resolve(self, db, client):
        """`PassRead.text` is the exact string every box's `char_start` and
        `char_end` count into. Losing it would leave every span on the page
        pointing at nothing, silently."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert_by_hand(db, doc, artifact)
        body = _read(client, doc.id)
        text = body["passes"][0]["text"]
        assert text == "Primero. Segundo. Tercero."
        first = body["segments"][0]
        assert text[first["anchor"]["char_start"]:first["anchor"]["char_end"]] == "Primero."

    def test_page_numbers_survive_so_a_pdf_still_filters_by_page(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert_by_hand(db, doc, artifact)
        body = _read(client, doc.id)
        assert [s["page_index"] for s in body["segments"]] == [0, 1, 1]

    def test_box_indexes_stay_dense_so_the_app_can_draw_the_pass(self, db, client):
        """`SegmentDisplay.geometry` refuses a pass whose box indexes are not
        exactly `0..count`. The seam re-enumerates, so they always are."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert_by_hand(db, doc, artifact)
        body = _read(client, doc.id)
        assert [s["box_index"] for s in body["segments"]] == [0, 1, 2]


class TestADanglingMarkerRefuses:
    def test_a_marker_naming_no_pass_refuses_rather_than_serving_the_block(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        artifact.geometry_superseded_by_pass_id = "no-such-pass"
        db.save(artifact)
        r = client.get(f"/api/segments/document/{doc.id}")
        assert r.status_code == 409, r.text
        assert artifact.id in r.text, "the answer must name the page that needs repair"

    def test_a_marker_naming_a_deleted_pass_refuses(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        pass_row = _convert_by_hand(db, doc, artifact)
        pass_row.deleted_at = utc_now()
        db.save(pass_row)
        r = client.get(f"/api/segments/document/{doc.id}")
        assert r.status_code == 409, r.text

    def test_the_stale_block_is_never_in_the_refused_answer(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        artifact.geometry_superseded_by_pass_id = "no-such-pass"
        db.save(artifact)
        r = client.get(f"/api/segments/document/{doc.id}")
        assert "Primero." not in r.text


class TestTheTextFillRefusesAnotherDocumentsWords:
    """#4958. `segment.pass_create` does not check that `source_artifact_id`
    belongs to `document_id`, so a pass on document A can name document B's
    artifact. With the text fill in place that becomes a READ LEAK."""

    def test_a_pass_naming_another_documents_artifact_serves_no_text(self, db, client, caplog):
        page_a = _make_doc(db, "a.jpg")
        page_b = _make_doc(db, "b.jpg")
        secret = OCRGeometryResult(
            provider="qwen",
            text="THE OTHER DOCUMENTS WORDS",
            boxes=[
                OCRGeometryBox(text="THE OTHER DOCUMENTS WORDS", bbox=[0.1, 0.1, 0.2, 0.05])
            ],
        )
        artifact_b = _artifact(db, page_b, secret)

        # A pass on A that points at B's artifact, exactly what the
        # unchecked action allows today.
        pass_row = SegmentPass(
            document_id=page_a.id, name="borrowed",
            provenance_kind=ProvenanceKind.unknown, source_artifact_id=artifact_b.id,
        )
        db.save(pass_row)
        _, rows = rows_from_reads(*segments_from_result(
            document_id=page_a.id, artifact_id=artifact_b.id, result=secret,
            provider="qwen", model=None, run_id=None, created_at=None,
            artifact_type="transcription",
        ))
        for row in rows:
            row.pass_id = pass_row.id
            db.save(row)

        with caplog.at_level("WARNING"):
            body = _read(client, page_a.id)

        borrowed = [s for s in body["segments"] if s["pass_id"] == pass_row.id]
        assert borrowed, "the segments themselves are still served"
        assert all(s["text"] is None for s in borrowed), "another document's words leaked"
        this_pass = [p for p in body["passes"] if p["id"] == pass_row.id][0]
        assert this_pass["text"] is None
        assert "THE OTHER DOCUMENTS WORDS" not in str(body)
        assert "#4958" in caplog.text, "a refusal must be logged, never silent"

    def test_a_pass_naming_this_documents_own_artifact_does_get_its_words(self, db, client):
        """The positive control: without it, a seam that refused EVERY text
        fill would pass the test above."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert_by_hand(db, doc, artifact)
        body = _read(client, doc.id)
        assert [s["text"] for s in body["segments"]] == ["Primero.", "Segundo.", "Tercero."]


class TestReadingStillWritesNothing:
    def test_reading_a_converted_page_ten_times_changes_no_row(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert_by_hand(db, doc, artifact)
        before = db.get(Artifact, artifact.id).model_dump(mode="json")
        first = _read(client, doc.id)
        for _ in range(9):
            assert _read(client, doc.id) == first
        assert db.get(Artifact, artifact.id).model_dump(mode="json") == before
