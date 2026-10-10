"""`normalized_text` is a transcription at a level, not a kind (`source.reading.normalized-text-is-a-level`,
#5653, ruled 2026-10-10).

Real libraries hold readings stored under the kind `normalized_text` (the Clean text tool and the
Modernización preset wrote them). They are never rewritten: they READ as kind transcription, level
regularised (their own level kept when they recorded one) everywhere readings are listed, counted and
exported; a write under the old kind is stored as that; and a filter that still names the old kind is
answered with them, so the app and old API callers keep finding what they found.

Built on the real Spanish notarial corpus page, imported through `format.import` as a person imports it.
"""
from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.content_representations import list_representations
from fichero_server.api.routes.document.segment_readings import (
    counting_by_kind,
    counting_by_kind_and_level,
    counting_texts,
    document_text,
    list_segment_readings,
    ordered_lines,
    readings_of_segment,
    working_pass,
)
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, ReadingChoice, Status
from fichero_server.page_export import export_page, page_from_library

pytestmark = pytest.mark.source_model

PAGE = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus" / "transkribus_spanish-notarial_0074.page.xml"
PERSON = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
REGULARISED = "hizieron donacion a la dicha Anna Maria su"


@pytest.fixture
def line(db, tmp_path):
    """The corpus line `hizieron donacion a la dha$.dicha $ant:Anna $ant:Maria su`, imported."""
    doc = Document(name="0074.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path=str(tmp_path / "0074.jpg"), status=Status.completed)
    db.save(doc)
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(PAGE)}, PERSON)
    rows = ordered_lines(db, working_pass(db, doc.id).pass_id)
    for row in rows:
        texts = [item.content for item in readings_of_segment(db, row.id) if item.kind == "transcription"]
        if any(text.startswith("hizieron donacion") for text in texts):
            return row
    raise AssertionError("the corpus line was not imported")


def _stored(db, model, row_id: str) -> tuple:
    """The row's kind (and level) AS STORED, read past the model: what the library file holds."""
    columns = "kind, level" if model is ContentRepresentation else "kind"
    return tuple(db.execute_fetchone(
        f"SELECT {columns} FROM {db._sql_table_name(model)} WHERE id = $id", {"id": row_id}))


def _old_row(db, segment, content: str = REGULARISED, level: str | None = None) -> str:
    """A reading stored under `normalized_text` the way the old writers stored it. Built valid and then
    given the old kind with no validation, because the model no longer writes that kind."""
    row = ContentRepresentation(document_id=segment.document_id, segment_id=segment.id, kind="transcription",
                                content=content, source_anchor=segment.anchor.model_copy())
    row = row.model_copy(update={"kind": "normalized_text", "level": level})
    db.save(row)
    assert _stored(db, ContentRepresentation, row.id) == ("normalized_text", level)
    return row.id


def _as_written_text(db, segment) -> str:
    items = readings_of_segment(db, segment.id)
    answer = counting_by_kind(db, segment.id, items)["transcription"]
    return next(i.content for i in items if i.id == answer.representation_id)


class TestOldRowsReadAsATranscriptionAtALevel:
    def test_an_old_row_lists_as_a_transcription_regularised_and_is_never_rewritten(self, db, line):
        """WHY: the kind is a level (ruled 2026-10-10). Read as its own kind, it stayed outside every
        transcription list and count; rewritten, a real library's rows would be migrated under it."""
        old = _old_row(db, line)
        (read,) = [item for item in readings_of_segment(db, line.id) if item.id == old]
        assert (read.kind, read.level) == ("transcription", "regularised")
        row = db.get(ContentRepresentation, old)
        assert (row.kind, row.level) == ("transcription", "regularised")
        (listed,) = [r for r in asyncio.run(list_representations(line.document_id, db=db)).items if r.id == old]
        assert (listed.kind, listed.level) == ("transcription", "regularised")
        assert _stored(db, ContentRepresentation, old) == ("normalized_text", None), "the row is not rewritten"

    def test_an_old_row_that_recorded_a_level_keeps_it(self, db, line):
        """WHY: a level, where one was recorded, is the reading's own fact; the alias only fills a gap."""
        old = _old_row(db, line, "hicieron donación a la dicha Ana María su", level="modernised")
        (read,) = [item for item in readings_of_segment(db, line.id) if item.id == old]
        assert (read.kind, read.level) == ("transcription", "modernised")

    def test_it_counts_at_its_level_beside_the_line_as_written_never_over_it(self, db, line):
        """WHY: read as a transcription with no level, a machine's regularised text would compete with
        the line as written, and the page's text, its export and the Kraken set could lose `dha`."""
        as_written = _as_written_text(db, line)
        page_text = document_text(db, line.document_id).text
        old = _old_row(db, line)

        by_level = counting_by_kind_and_level(db, line.id, readings_of_segment(db, line.id))
        assert by_level[("transcription", "regularised")].representation_id == old
        assert by_level[("transcription", "as_written")].representation_id != old
        assert _as_written_text(db, line) == as_written and "dha" in as_written
        assert document_text(db, line.document_id).text == page_text
        listed = asyncio.run(list_segment_readings(line.id, kind=None, db=db))
        assert listed.counting["transcription"].representation_id != old
        assert "normalized_text" not in listed.counting


class TestTheOldKindStillFilters:
    def test_a_kind_normalized_text_filter_returns_those_readings(self, db, line):
        """WHY: the app and older API callers ask for `kind=normalized_text`. Read as a transcription,
        the filter came back empty -- so it is answered as the transcription at level regularised,
        keyed by the kind asked for."""
        old = _old_row(db, line)
        listed = asyncio.run(list_segment_readings(line.id, kind="normalized_text", db=db))
        assert [item.id for item in listed.items] == [old]
        assert listed.counting["normalized_text"].representation_id == old
        assert counting_texts(db, [line], "normalized_text") == {line.id: REGULARISED}
        assert REGULARISED in document_text(db, line.document_id, kind="normalized_text").text
        # The as-written transcription is not what the old kind names.
        assert counting_texts(db, [line], "transcription")[line.id] != REGULARISED

    def test_the_page_export_of_the_regularised_level_includes_old_rows(self, db, line):
        """WHY: an export of the regularised level that dropped every reading stored under the old kind
        would lose a library's normalised text without a word."""
        _old_row(db, line)
        for page, _choices in (
            page_from_library(db, line.document_id, reading_kind="transcription", reading_level="regularised"),
            page_from_library(db, line.document_id, reading_kind="normalized_text"),
        ):
            (segment,) = [s for s in page.segments if s.ref == line.id]
            assert segment.readings == [("transcription", REGULARISED)]
        written = export_page(db, line.document_id, "pagexml", reading_kind="normalized_text").data.decode()
        assert REGULARISED in written
        # The default export is still the line as written, counted first.
        default, _ = page_from_library(db, line.document_id)
        (segment,) = [s for s in default.segments if s.ref == line.id]
        assert segment.readings[0][1] == _as_written_text(db, line)
        ET.fromstring(written)  # a well-formed file


class TestWritesUnderTheOldKind:
    def test_a_write_under_normalized_text_is_stored_as_a_transcription_regularised(self, db, line):
        """WHY: a caller still sending the old kind must not make new rows of a kind that no longer is."""
        rid = registry.invoke(db, "representation.create", {
            "document_id": line.document_id, "segment_id": line.id, "kind": "normalized_text",
            "content": REGULARISED}, PERSON).result["id"]
        assert _stored(db, ContentRepresentation, rid) == ("transcription", "regularised")

    def test_a_choice_under_the_old_kind_is_a_choice_of_a_transcription_at_its_level(self, db, line):
        """WHY: a choice is per kind; one stored under the old kind would never be superseded by a
        choice of the transcription at the same level, and two choices would claim one level."""
        old = _old_row(db, line)
        stale = ReadingChoice(document_id=line.document_id, segment_id=line.id, kind="transcription",
                              representation_id=old, chosen_by="historian")
        stale = stale.model_copy(update={"kind": "normalized_text"})
        db.save(stale)
        assert db.get(ReadingChoice, stale.id).kind == "transcription"

        newer = registry.invoke(db, "representation.create", {
            "document_id": line.document_id, "segment_id": line.id, "kind": "transcription",
            "level": "regularised", "content": "hizieron donacion a la dicha Anna María su"}, PERSON).result["id"]
        made = registry.invoke(db, "reading.choose", {"segment_id": line.id, "kind": "normalized_text",
                                                      "representation_id": newer}, PERSON).result
        assert _stored(db, ReadingChoice, made["choice_id"]) == ("transcription",)
        live = [c for c in db.query(ReadingChoice, segment_id=line.id) if c.superseded_at is None]
        assert [c.representation_id for c in live] == [newer], "the old-kind choice is superseded"
        by_level = counting_by_kind_and_level(db, line.id, readings_of_segment(db, line.id))
        assert by_level[("transcription", "regularised")].representation_id == newer
        assert by_level[("transcription", "as_written")].representation_id not in (old, newer)
