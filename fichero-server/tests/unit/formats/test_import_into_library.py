"""Importing an interchange file INTO a library (#4943).

`source.format.import-is-pass`, `source.format.reimport-recognised`.

**This is the test that says the format work is a feature rather than a library.**
Until this path existed, `SourcePage` never left `formats/`: a file could be read
into a transient object and written back, and a user could not bring their
eScriptorium export into a library. Reading into the model is not reading into the
library.

The success paths use **OCR-D's ground truth** and the **ALTO project's own file**,
because eScriptorium's own samples turned out to be self-inconsistent — they declare
`imageHeight="206"` and place shapes past y=245, in both their PAGE XML and their
ALTO export. That is a finding rather than an obstacle, and it has its own test: an
import either happens or does not, and a file whose page size disagrees with its
coordinates is refused with both numbers named.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.reading_orders import as_written_order
from fichero_server.models import (
    ContentRepresentation,
    Document,
    DocType,
    FileType,
    Segment,
    Status,
)
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.reading_orders import ReadingOrderEntry
from fichero_server.models.segments import SegmentPass
import fichero_server.api.routes.document.format_import  # noqa: F401

pytestmark = pytest.mark.source_model

FIXTURES = Path(__file__).parent / "fixtures"
ESCRIPTORIUM = FIXTURES / "escriptorium_export.page.xml"
ESCRIPTORIUM_ALTO = FIXTURES / "escriptorium_export.alto.xml"
OCRD = FIXTURES / "ocrd_gt_aepinus_0020.page.xml"
ALTO_PROJECT = FIXTURES / "altoxml_glyph_00001.alto.xml"


def _person() -> ActionContext:
    return ActionContext(actor="historian", is_bootstrap=True)


def _document(db, name: str = "folio.jpg") -> Document:
    doc = Document(
        name=name, doc_type=DocType.file, file_type=FileType.image,
        path=f"/path/{name}", status=Status.completed,
    )
    db.save(doc)
    return doc


def _import(db, doc, source: Path, *, ctx: ActionContext | None = None, **extra):
    return registry.invoke(
        db,
        "format.import",
        {"document_id": doc.id, "path": str(source), **extra},
        ctx or _person(),
    ).result


class TestAnImportArrivesAsAPass:
    def test_a_real_file_becomes_a_pass_with_its_segments(self, db, tmp_path):
        doc = _document(db)
        copied = tmp_path / "my_export.xml"
        copied.write_bytes(OCRD.read_bytes())

        result = _import(db, doc, copied)

        assert result["format"] == "pagexml"
        assert result["segments"] > 0
        pass_row = db.get(SegmentPass, result["pass_id"])
        assert pass_row is not None
        rows = [r for r in db.query(Segment, pass_id=pass_row.id) if r.deleted_at is None]
        assert len(rows) == result["segments"]

    def test_the_pass_records_the_file_it_came_from(self, db, tmp_path):
        doc = _document(db)
        copied = tmp_path / "my_export.xml"
        copied.write_bytes(OCRD.read_bytes())

        result = _import(db, doc, copied)

        pass_row = db.get(SegmentPass, result["pass_id"])
        assert pass_row.import_file == "my_export.xml"
        assert pass_row.import_checksum == result["checksum"]
        assert pass_row.name == "my_export.xml"

    def test_a_person_importing_makes_it_theirs_and_a_runner_does_not(self, db, tmp_path):
        """One rule for who made this (#4868/#4869), not a second copy of it: a
        person brought a file, so the pass is theirs; a runner's import is a
        machine's."""
        doc = _document(db)
        mine = tmp_path / "mine.xml"
        mine.write_bytes(OCRD.read_bytes())
        theirs = tmp_path / "theirs.xml"
        theirs.write_bytes(ALTO_PROJECT.read_bytes())

        person = _import(db, doc, mine)
        runner = _import(
            db, doc, theirs,
            ctx=ActionContext(actor="runner", run_id="run-1", is_bootstrap=True),
        )

        assert db.get(SegmentPass, person["pass_id"]).provenance_kind == ProvenanceKind.human
        assert db.get(SegmentPass, runner["pass_id"]).provenance_kind != ProvenanceKind.human

    def test_it_does_NOT_become_the_working_pass(self, db, tmp_path):
        """Ruled 2026-09-26: **arriving is not winning.** Promoting an import would
        answer a scholarly question — which reading of this page counts — with a file
        operation, and curation is what decides that."""
        from fichero_server.models import SegmentPassChoice

        doc = _document(db)
        copied = tmp_path / "e.xml"
        copied.write_bytes(OCRD.read_bytes())

        result = _import(db, doc, copied)

        choices = [
            c for c in db.query(SegmentPassChoice, document_id=doc.id)
            if c.pass_id == result["pass_id"]
        ]
        assert choices == [], "the import promoted itself to the working pass"

    def test_it_overwrites_nothing(self, db, tmp_path):
        """An import is another opinion about the page, which is what a pass is for.
        The segments and readings that were there stay exactly as they were."""
        doc = _document(db)
        existing_pass = SegmentPass(
            document_id=doc.id, name="a hand", provenance_kind=ProvenanceKind.human
        )
        db.save(existing_pass)
        before = {r.id for r in db.query(Segment, pass_id=existing_pass.id)}

        copied = tmp_path / "e.xml"
        copied.write_bytes(OCRD.read_bytes())
        _import(db, doc, copied)

        after = {r.id for r in db.query(Segment, pass_id=existing_pass.id)}
        assert after == before
        assert db.get(SegmentPass, existing_pass.id).deleted_at is None


class TestWhatSlicesNineAndTenGiveTheImport:
    """The moment the programme pays off: an imported file's language, script,
    direction and reading order arrive as the model's own facts."""

    def test_the_readings_arrive_as_readings(self, db, tmp_path):
        doc = _document(db)
        copied = tmp_path / "e.xml"
        copied.write_bytes(OCRD.read_bytes())

        result = _import(db, doc, copied)

        readings = db.query(ContentRepresentation, document_id=doc.id)
        assert len(readings) == result["readings"] > 0
        assert all(r.content.strip() for r in readings)

    def test_an_imported_fact_says_the_FILE_said_so(self, db, tmp_path):
        """Not `user` (no person judged it) and not `detected` (nothing ran a
        detector): `metadata`, because the file stated it. That distinction is what
        lets a curator see which languages came from an import."""
        from fichero_server.llm.language_policy import SOURCE_METADATA

        doc = _document(db)
        copied = tmp_path / "ocrd.xml"
        copied.write_bytes(OCRD.read_bytes())

        result = _import(db, doc, copied)

        rows = [
            r for r in db.query(Segment, pass_id=result["pass_id"])
            if r.language is not None
        ]
        assert rows, "the OCR-D file states German on its regions"
        assert all(r.language_meta["source"] == SOURCE_METADATA for r in rows)
        assert all("imported pagexml file" in r.language_meta["basis"] for r in rows)

    def test_the_files_reading_order_becomes_a_named_order(self, db, tmp_path):
        """Slice 10 is what makes this expressible. Without named orders the file's
        `ReadingOrder` would have nowhere to go."""
        doc = _document(db)
        copied = tmp_path / "ocrd.xml"
        copied.write_bytes(OCRD.read_bytes())

        result = _import(db, doc, copied)

        order = as_written_order(db, result["pass_id"])
        assert order is not None
        entries = db.query(ReadingOrderEntry, order_id=order.id)
        assert len(entries) == result["order_entries"] > 0
        # In the FILE's sequence, which is the claim the file makes.
        assert [e.position for e in sorted(entries, key=lambda e: e.position)] == [
            float(i + 1) for i in range(len(entries))
        ]

    def test_unrecognised_content_rides_along_on_the_segment(self, db, tmp_path):
        """`keeps-unrecognised` survives the import too: OCR-D's
        `custom="readingOrder {index:0;} structure {type:heading;}"` is on the imported
        segment, so a later export back to PAGE XML can write it."""
        doc = _document(db)
        copied = tmp_path / "e.xml"
        copied.write_bytes(OCRD.read_bytes())

        result = _import(db, doc, copied)

        rows = db.query(Segment, pass_id=result["pass_id"])
        kept = [r for r in rows if r.metadata.get("foreign")]
        assert kept, "the file's custom attributes did not survive the import"


class TestReimportIsRecognised:
    def test_the_same_file_twice_is_refused_not_duplicated(self, db, tmp_path):
        doc = _document(db)
        copied = tmp_path / "e.xml"
        copied.write_bytes(OCRD.read_bytes())
        first = _import(db, doc, copied)

        with pytest.raises(HTTPException) as raised:
            _import(db, doc, copied)

        assert raised.value.status_code == 409
        assert first["pass_id"] in str(raised.value.detail)
        # Nothing written by the second attempt.
        passes = [p for p in db.query(SegmentPass, document_id=doc.id) if p.deleted_at is None]
        assert len(passes) == 1

    def test_a_renamed_copy_of_the_same_content_is_still_recognised(self, db, tmp_path):
        """The mechanism is the CONTENT hash (→ #739), so renaming does not make it a
        different file — which is what a user does when they export twice."""
        doc = _document(db)
        first_path = tmp_path / "export.xml"
        first_path.write_bytes(OCRD.read_bytes())
        _import(db, doc, first_path)

        renamed = tmp_path / "export (1).xml"
        renamed.write_bytes(OCRD.read_bytes())
        with pytest.raises(HTTPException) as raised:
            _import(db, doc, renamed)
        assert raised.value.status_code == 409

    def test_a_DIFFERENT_file_on_the_same_document_is_accepted(self, db, tmp_path):
        doc = _document(db)
        one = tmp_path / "one.xml"
        one.write_bytes(OCRD.read_bytes())
        two = tmp_path / "two.xml"
        two.write_bytes(ALTO_PROJECT.read_bytes())

        _import(db, doc, one)
        second = _import(db, doc, two)

        assert second["segments"] > 0
        passes = [p for p in db.query(SegmentPass, document_id=doc.id) if p.deleted_at is None]
        assert len(passes) == 2

    def test_the_same_file_on_a_DIFFERENT_document_is_accepted(self, db, tmp_path):
        """The hash is scoped to the document: the same transcription of two folios is
        two imports, and refusing the second would be wrong."""
        first_doc = _document(db, "folio_1.jpg")
        second_doc = _document(db, "folio_2.jpg")
        copied = tmp_path / "e.xml"
        copied.write_bytes(OCRD.read_bytes())

        _import(db, first_doc, copied)
        again = _import(db, second_doc, copied)

        assert again["segments"] > 0


class TestRefusals:
    def test_a_file_nothing_recognises_names_what_is_readable(self, db, tmp_path):
        doc = _document(db)
        odd = tmp_path / "notes.rtf"
        odd.write_bytes(b"{\\rtf1 this is not an interchange file}")

        with pytest.raises(HTTPException) as raised:
            _import(db, doc, odd)
        assert raised.value.status_code == 422
        assert "pagexml" in str(raised.value.detail)

    def test_a_missing_file_is_a_404(self, db, tmp_path):
        doc = _document(db)

        with pytest.raises(HTTPException) as raised:
            _import(db, doc, tmp_path / "absent.xml")
        assert raised.value.status_code == 404

    def test_a_missing_document_is_a_404(self, db, tmp_path):
        copied = tmp_path / "e.xml"
        copied.write_bytes(OCRD.read_bytes())

        with pytest.raises(HTTPException) as raised:
            registry.invoke(
                db,
                "format.import",
                {"document_id": "no-such-doc", "path": str(copied)},
                _person(),
            )
        assert raised.value.status_code == 404

    def test_undoing_an_import_removes_its_pass(self, db, tmp_path):
        doc = _document(db)
        copied = tmp_path / "e.xml"
        copied.write_bytes(OCRD.read_bytes())
        result = _import(db, doc, copied)

        registry.invoke(db, "segment.pass_delete", {"pass_id": result["pass_id"]}, _person())

        assert db.get(SegmentPass, result["pass_id"]).deleted_at is not None


class TestAFileThatDisagreesWithItselfIsRefused:
    """**eScriptorium's own samples declare a page smaller than their coordinates** —
    `imageHeight="206"` with shapes past y=245, in both their PAGE XML and their ALTO
    export. Verified in both files.

    A segment IS a place on a source, so there are three possible answers and two of
    them are wrong: invent a place (puts a scholar's block where it is not), drop it
    silently (loses their transcription), or refuse and name what disagrees. The
    standing rule is to raise rather than substitute.
    """

    def test_the_refusal_names_the_page_size_and_the_segment(self, db, tmp_path):
        doc = _document(db)
        copied = tmp_path / "escriptorium.xml"
        copied.write_bytes(ESCRIPTORIUM.read_bytes())

        with pytest.raises(HTTPException) as raised:
            _import(db, doc, copied)

        message = str(raised.value.detail)
        assert raised.value.status_code == 422
        assert "864x206" in message
        assert "eSc_textblock_03" in message
        assert "only its author can say which is right" in message

    def test_nothing_is_written_when_a_file_is_refused(self, db, tmp_path):
        """An import either happens or does not: a pass holding half a page's segments
        is worse than no pass, so the check runs before the first write."""
        doc = _document(db)
        copied = tmp_path / "escriptorium.xml"
        copied.write_bytes(ESCRIPTORIUM.read_bytes())

        with pytest.raises(HTTPException):
            _import(db, doc, copied)

        assert [p for p in db.query(SegmentPass, document_id=doc.id) if p.deleted_at is None] == []
        assert db.query(Segment, document_id=doc.id) == []

    def test_their_alto_export_has_the_same_inconsistency(self, db, tmp_path):
        """Both exports, same sample data, same disagreement — so it is the fixture's
        own geometry rather than one writer's bug."""
        doc = _document(db)
        copied = tmp_path / "escriptorium.alto.xml"
        copied.write_bytes(ESCRIPTORIUM_ALTO.read_bytes())

        with pytest.raises(HTTPException) as raised:
            _import(db, doc, copied)
        assert raised.value.status_code == 422


class TestRealFilesHaveUnusableShapesAndTheTwoCasesDiffer:
    """**A shape outside the page and a shape with no area are different facts.**

    Both appear in real files. eScriptorium's exports place blocks past their declared
    `imageHeight`; the ALTO project's own file writes `WIDTH="0"` for a page number.
    Treating them the same would be either too strict (losing a transcription over a
    rounding artefact) or too loose (inventing a place for a block that has none).
    """

    def test_a_zero_width_box_inside_the_page_is_widened_and_recorded(self, db, tmp_path):
        """The PLACE is real and only the extent is unusable, so the segment is kept
        with one unit of the file's own grid — not a round number of ours, which would
        be our shape rather than a repair of theirs."""
        doc = _document(db)
        copied = tmp_path / "alto.xml"
        copied.write_bytes(ALTO_PROJECT.read_bytes())

        result = _import(db, doc, copied)

        rows = db.query(Segment, pass_id=result["pass_id"])
        widened = [r for r in rows if "no area in the file" in (r.metadata.get("geometry_problem") or "")]
        assert widened, "the file's zero-width box was not recorded as repaired"
        assert all(r.bbox_w > 0 and r.bbox_h > 0 for r in rows)
        # And the text of that box survived, which is the point of not refusing.
        readings = db.query(ContentRepresentation, document_id=doc.id)
        assert any(r.content == "81" for r in readings)

    def test_a_block_outside_the_page_refuses_the_whole_import_instead(self, db, tmp_path):
        """The other case, asserted beside it: no clamping produces a drawable shape,
        so there is nothing to record and nothing honest to write."""
        doc = _document(db)
        copied = tmp_path / "escriptorium.xml"
        copied.write_bytes(ESCRIPTORIUM.read_bytes())

        with pytest.raises(HTTPException) as raised:
            _import(db, doc, copied)
        assert "lie outside it" in str(raised.value.detail)

    def test_the_repair_is_the_smallest_the_file_can_express(self, db, tmp_path):
        """One pixel of the page the file declares. The mm10 file states no pixel grid,
        so it gets the documented fallback rather than a silent one."""
        from fichero_server.api.routes.document.format_import import _minimum_extent

        assert _minimum_extent((1000, 2000)) == (1 / 1000, 1 / 2000)
        assert _minimum_extent(None) == (1e-4, 1e-4)


class TestTheImportRoute:
    """`source.format.everywhere`, the app's half: until this route existed a person
    could EXPORT from the app and not import, which is an odd shape for a programme
    whose target is reading and writing four formats."""

    def test_a_person_uploads_a_file_and_gets_a_pass(self, db, client):
        doc = _document(db)

        response = client.post(
            f"/api/documents/{doc.id}/import",
            files={"file": ("aepinus.xml", OCRD.read_bytes(), "application/xml")},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["format"] == "pagexml"
        assert body["segments"] > 0
        assert db.get(SegmentPass, body["pass_id"]) is not None

    def test_the_pass_is_named_after_the_file_the_person_chose(self, db, client):
        """Not the temporary copy: a list of passes reading `fichero-import-8h2k.xml`
        would tell a scholar nothing about which file they brought."""
        doc = _document(db)

        response = client.post(
            f"/api/documents/{doc.id}/import",
            files={"file": ("my folio 12r.xml", OCRD.read_bytes(), "application/xml")},
        )

        pass_row = db.get(SegmentPass, response.json()["pass_id"])
        assert pass_row.name == "my folio 12r.xml"

    def test_the_recognised_format_is_reported_even_for_a_renamed_file(self, db, client):
        """The answer to "did it read my file properly": the bytes decide, so a
        renamed export still reports what it actually is."""
        doc = _document(db)

        response = client.post(
            f"/api/documents/{doc.id}/import",
            files={"file": ("notes.txt", OCRD.read_bytes(), "text/plain")},
        )

        assert response.status_code == 200, response.text
        assert response.json()["format"] == "pagexml"

    def test_repaired_geometry_is_surfaced_rather_than_buried_in_rows(self, db, client):
        """A page where boxes were repaired is a page somebody should look at, so the
        count comes back with the import instead of living only in row metadata."""
        doc = _document(db)

        response = client.post(
            f"/api/documents/{doc.id}/import",
            files={"file": ("alto.xml", ALTO_PROJECT.read_bytes(), "application/xml")},
        )

        assert response.status_code == 200, response.text
        assert response.json()["geometry_problems"] >= 1

    def test_a_second_upload_of_the_same_file_is_refused_with_409(self, db, client):
        doc = _document(db)
        payload = {"file": ("e.xml", OCRD.read_bytes(), "application/xml")}

        assert client.post(f"/api/documents/{doc.id}/import", files=payload).status_code == 200
        again = client.post(f"/api/documents/{doc.id}/import", files=payload)

        assert again.status_code == 409
        assert "already on this document" in again.text

    def test_an_unreadable_upload_is_refused_with_422(self, db, client):
        doc = _document(db)

        response = client.post(
            f"/api/documents/{doc.id}/import",
            files={"file": ("notes.rtf", b"{\\rtf1 not an interchange file}", "text/rtf")},
        )

        assert response.status_code == 422
        assert "pagexml" in response.text

    def test_the_temporary_copy_is_removed_even_when_the_import_refuses(self, db, client, tmp_path):
        """An import that refuses should leave nothing behind, least of all a copy of a
        scholar's file in a temp directory."""
        import glob
        import tempfile

        doc = _document(db)
        before = set(glob.glob(str(Path(tempfile.gettempdir()) / "fichero-import-*")))

        client.post(
            f"/api/documents/{doc.id}/import",
            files={"file": ("bad.rtf", b"{\\rtf1 nope}", "text/rtf")},
        )

        after = set(glob.glob(str(Path(tempfile.gettempdir()) / "fichero-import-*")))
        assert after == before
