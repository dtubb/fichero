"""A line reads from its words when the file gave text only to the words (#5433).

Spec: `formats-and-training.md` -- `source.reading.line-from-its-words`.

WHY: word readings retire in favour of LINE readings (ruled 2026-09-28), and every surface that
lists lines (the segment list, the Inspector's Text) reads the LINE's reading. An ALTO, hOCR or
PAGE file that carries text only on its words (an ALTO `String@CONTENT` under a `TextLine` with no
text of its own, which is every ABBYY/docWorks ALTO) left every line "No reading" while its words
said "Počinagiſie knihy Geneſis" (the Acceptance library's paderov-mm10 page). If this regresses,
an imported page looks unread line by line although its whole text is there.

Everything goes through the real import route (`POST /api/documents/{id}/import`), the real
segments route the segment list reads and the real readings route the Inspector reads. The
conversion half opens a temporary library through a PRIVATE `DatabaseManager`, never a real one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action and route)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document import segment_readings
from fichero_server.db import Database
from fichero_server.db.manager import DatabaseManager
from fichero_server.formats import read_page
from fichero_server.maintenance import conversion_on_open
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, Segment, Status

pytestmark = pytest.mark.source_model

FIXTURES = Path(__file__).parent / "fixtures"
#: Real ALTO in `mm10` with text ONLY on its `String`s: the same shape as the paderov-mm10 page.
WORDS_ONLY_ALTO = FIXTURES / "altoxml_glyph_00001.alto.xml"
#: Real PAGE XML whose lines carry their OWN TextEquiv as well as their words'.
LINES_AND_WORDS_PAGE = FIXTURES / "ocrd_gt_aepinus_0020.page.xml"
ALTO_NS = "{http://www.loc.gov/standards/alto/ns-v2#}"

#: A right-to-left line whose words the file lists LEFT TO RIGHT across the page (visual order):
#: "עולם" at x=100, "שלום" at x=500. Read right to left the line says "שלום עולם".
RTL_ALTO = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
  <Description><MeasurementUnit>pixel</MeasurementUnit></Description>
  <Layout>
    <Page ID="p1" WIDTH="1000" HEIGHT="500" PHYSICAL_IMG_NR="1">
      <PrintSpace>
        <TextBlock ID="b1" HPOS="50" VPOS="50" WIDTH="900" HEIGHT="200">
          <TextLine ID="l1" HPOS="100" VPOS="100" WIDTH="800" HEIGHT="50">
            <String ID="w1" HPOS="100" VPOS="100" WIDTH="300" HEIGHT="50" CONTENT="עולם"/>
            <SP/>
            <String ID="w2" HPOS="500" VPOS="100" WIDTH="300" HEIGHT="50" CONTENT="שלום"/>
          </TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>
""".encode()


def _page(db, name: str = "00000013.jpg") -> str:
    doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image,
                   path=f"/p/{name}", status=Status.completed)
    db.save(doc)
    return doc.id


def _upload(client, doc_id: str, name: str, data: bytes) -> str:
    response = client.post(f"/api/documents/{doc_id}/import", files={"file": (name, data, "application/xml")})
    assert response.status_code == 200, response.text
    return response.json()["pass_id"]


def _segments(client, doc_id: str, pass_id: str) -> list[dict]:
    """The rows the app's segment list draws, with the `text` it shows ("No reading" when None)."""
    body = client.get(f"/api/segments/document/{doc_id}").json()
    return [s for s in body["segments"] if s["pass_id"] == pass_id]


def _expected_line_texts(path: Path) -> list[str]:
    """Each TextLine's Strings joined in the file's order -- worked out from the file, not hard-coded."""
    root = etree.parse(str(path)).getroot()
    return [
        " ".join(s.get("CONTENT") for s in line.iter(f"{ALTO_NS}String") if s.get("CONTENT"))
        for line in root.iter(f"{ALTO_NS}TextLine")
    ]


class TestWordsOnlyGiveTheLineAReading:
    def test_every_line_reads_its_words_joined_in_the_files_order(self, db, client):
        """The paderov case: an mm10 ALTO with text only on its words. Every line the segment list
        draws must carry its words' text, in the order the file gives them, so no row says
        "No reading" while its words have text."""
        doc_id = _page(db)
        pass_id = _upload(client, doc_id, "00000013.xml", WORDS_ONLY_ALTO.read_bytes())

        lines = [s for s in _segments(client, doc_id, pass_id) if s["kind"] == "line"]
        expected = _expected_line_texts(WORDS_ONLY_ALTO)
        assert len(lines) == len(expected)
        unread = [s["id"] for s in lines if not s["text"]]
        assert not unread, f"{len(unread)} lines still say 'No reading' while their words have text"
        assert sorted(s["text"] for s in lines) == sorted(expected)
        assert any(text.startswith("So sollen sie") for text in (s["text"] for s in lines))

    def test_the_inspector_reads_the_lines_reading_and_it_counts(self, db, client):
        """The Inspector's Text reads `/api/segments/{id}/readings`: the line's composed reading is
        there, and it is the one that COUNTS, or the Inspector still shows "No reading"."""
        doc_id = _page(db)
        pass_id = _upload(client, doc_id, "00000013.xml", WORDS_ONLY_ALTO.read_bytes())
        line = next(s for s in _segments(client, doc_id, pass_id)
                    if s["kind"] == "line" and (s["text"] or "").startswith("So sollen sie"))

        body = client.get(f"/api/segments/{line['id']}/readings").json()
        [reading] = [item for item in body["items"] if item["kind"] == "transcription"]
        assert reading["content"] == line["text"]
        assert body["counting"]["transcription"]["representation_id"] == reading["id"]
        # The file's text, not a person's: a composed line must never claim someone typed it.
        assert reading["provenance_kind"] == "external_import"

    def test_the_words_keep_their_boxes_and_their_own_text(self, db, client):
        """Composing the line touches only the line: each word keeps the box and the text the file
        gave it, or the line's reading would have been bought with the page's geometry."""
        doc_id = _page(db)
        pass_id = _upload(client, doc_id, "00000013.xml", WORDS_ONLY_ALTO.read_bytes())
        file_words = [s for s in read_page("alto", WORDS_ONLY_ALTO.read_bytes()).segments if s.kind == "word"]

        words = [s for s in _segments(client, doc_id, pass_id) if s["kind"] == "word"]
        assert len(words) == len(file_words)
        assert sorted(w["text"] for w in words) == sorted(dict(s.readings)["transcription"] for s in file_words)
        first = next(w for w in words if w["text"] == "So")
        assert first["anchor"]["rect"] == pytest.approx([162 / 1003, 171 / 1469, 36 / 1003, 23 / 1469])

    def test_a_right_to_left_line_joins_its_words_right_to_left(self, db, client):
        """A Hebrew line whose file lists its words left to right across the page: the line is read
        right to left, so its reading starts with the RIGHTMOST word. Joined in the file's order it
        would say "עולם שלום", which is the line backwards."""
        doc_id = _page(db, "hebrew.jpg")
        pass_id = _upload(client, doc_id, "hebrew.alto.xml", RTL_ALTO)

        [line] = [s for s in _segments(client, doc_id, pass_id) if s["kind"] == "line"]
        assert line["text"] == "שלום עולם"


class TestNothingReadsTheLineTwice:
    def test_the_page_text_and_every_export_hold_each_word_once(self, db, client):
        """The sweep (fix then siblings): now that a words-only line has a reading AND its words do,
        anything that writes every reading would put the line on the page twice. The page's text
        (search, embeddings, extraction and CER all read it) takes the finest level; PAGE XML holds
        line and word TextEquiv by design, one per level; hOCR wrote the line's text beside its word
        spans, so any hOCR consumer read every word twice, until the writer skipped it."""
        from fichero_server.api.routes.document.segment_readings import document_text
        from fichero_server.page_export import export_page

        doc_id = _page(db)
        pass_id = _upload(client, doc_id, "00000013.xml", WORDS_ONLY_ALTO.read_bytes())
        once = WORDS_ONLY_ALTO.read_text().count('CONTENT="sollen"')
        assert once >= 1

        assert document_text(db, doc_id).text.count("sollen") == once
        assert (db.get(Document, doc_id).page_content or "").count("sollen") == once
        for fmt in ("alto", "tei", "hocr"):
            written = export_page(db, doc_id, fmt, pass_id=pass_id).data.decode("utf-8")
            assert written.count("sollen") == once, f"{fmt} export writes the line's words twice"


class TestALineTheFileReadIsUnchanged:
    def test_a_line_with_its_own_text_keeps_exactly_that_text(self, db, client):
        """PAGE XML gives the line its own TextEquiv beside its words'. That text is the line's
        reading, alone: composing a second one would put a rival reading on every line."""
        doc_id = _page(db, "aepinus.jpg")
        pass_id = _upload(client, doc_id, "aepinus.page.xml", LINES_AND_WORDS_PAGE.read_bytes())
        file_lines = [s for s in read_page("pagexml", LINES_AND_WORDS_PAGE.read_bytes()).segments if s.kind == "line"]
        assert all(s.readings for s in file_lines), "the fixture no longer gives every line its own text"

        lines = [s for s in _segments(client, doc_id, pass_id) if s["kind"] == "line"]
        assert sorted(s["text"] for s in lines) == sorted(dict(s.readings)["transcription"] for s in file_lines)
        for line in lines:
            body = client.get(f"/api/segments/{line['id']}/readings").json()
            assert body["count"] == 1, f"line {line['id']} gained a second reading"


class TestTheConversionOnOpenFillsAnExistingLibrary:
    def test_opening_a_library_imported_before_the_fix_gives_its_lines_their_readings(self, tmp_path, monkeypatch):
        """A library imported before this fix has lines with no reading. The running engine's
        conversion on open (#5222's one path) fills them, once: a second open adds nothing, and a
        line the file gave text is left alone."""
        monkeypatch.delenv("FICHERO_SKIP_PROJECT_CONVERSION", raising=False)
        # Chunks smaller than the page's 27 lines, so the open must walk several (an archive of
        # ~80,000 pages is ~2M lines and is never one transaction).
        monkeypatch.setattr(segment_readings, "LINE_CHUNK", 10)
        from tests.unit.maintenance.test_project_conversion_resume import _snapshot_stub

        package = tmp_path / "Acceptance.fichero"
        package.mkdir()
        db = Database(package / "fichero.duckdb")
        ctx = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
        words_only = _page(db)
        registry.invoke(db, "format.import", {"document_id": words_only, "path": str(WORDS_ONLY_ALTO)}, ctx)
        own_text = _page(db, "aepinus.jpg")
        registry.invoke(db, "format.import", {"document_id": own_text, "path": str(LINES_AND_WORDS_PAGE)}, ctx)
        # As the library was before this fix: the composed line readings are not there.
        lines = {row.id for row in db.query(Segment, document_id=words_only) if row.kind == "line"}
        for reading in db.query(ContentRepresentation, document_id=words_only):
            if reading.segment_id in lines:
                db.delete(reading)
        own_before = len(db.query(ContentRepresentation, document_id=own_text))
        db.close()
        _snapshot_stub(package, monkeypatch)

        manager = DatabaseManager()
        try:
            db = _open_and_wait(manager, package)
            read_lines = {r.segment_id for r in db.query(ContentRepresentation, document_id=words_only)}
            assert lines <= read_lines, f"{len(lines - read_lines)} lines still have no reading after the open"
            assert len(db.query(ContentRepresentation, document_id=own_text)) == own_before
            after_first = len(db.query(ContentRepresentation, document_id=words_only))
            conversion_on_open.stop(package)
            manager.close_all()

            db = _open_and_wait(manager, package)
            assert len(db.query(ContentRepresentation, document_id=words_only)) == after_first, (
                "a second open composed the lines again")
        finally:
            conversion_on_open.stop(None)
            manager.close_all()


class TestItWorksInChunksAndStopsBetweenThem:
    def test_a_stop_after_the_first_chunk_leaves_the_rest_for_the_next_open(self, db, monkeypatch):
        """A quit mid-way (the library closing sets the stop event) must lose at most one chunk and
        leave nothing half-written: the first chunk's lines read, the others are still unread, and
        the next run fills exactly those. Without chunks a 2M-line archive is one transaction that a
        quit throws away whole; without the stop check, closing a library waits for all of it."""
        monkeypatch.setattr(segment_readings, "LINE_CHUNK", 10)
        doc_id = _page(db)
        ctx = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
        registry.invoke(db, "format.import", {"document_id": doc_id, "path": str(WORDS_ONLY_ALTO)}, ctx)
        lines = {row.id for row in db.query(Segment, document_id=doc_id) if row.kind == "line"}
        for reading in db.query(ContentRepresentation, document_id=doc_id):
            if reading.segment_id in lines:
                db.delete(reading)
        assert len(lines) > 10, "the fixture must hold more lines than a chunk"

        asked = []

        def stop_after_the_first_chunk() -> bool:
            asked.append(True)
            return len(asked) > 1

        written = segment_readings.compose_line_readings(db, should_stop=stop_after_the_first_chunk)

        def read_lines() -> set[str]:
            return {r.segment_id for r in db.query(ContentRepresentation, document_id=doc_id)} & lines

        assert written == 10 and len(read_lines()) == 10, "a stop between chunks must keep exactly one chunk"
        assert segment_readings.compose_line_readings(db) == len(lines) - 10
        assert read_lines() == lines


def _open_and_wait(manager: DatabaseManager, package: Path) -> Database:
    db = manager.get_database(package)
    thread = conversion_on_open._runs.get(manager._cache_key(package), (None,))[0]
    assert thread is not None, "opening started no conversion"
    thread.join(120)
    assert not thread.is_alive()
    return db
