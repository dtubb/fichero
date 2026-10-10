"""Reading levels (ruled 2026-10-10): five ship, they are a checked list, and "which reading counts" is
worked out per kind AND level (`source.reading.levels`, `source.reading.counts-per-level`).

Built on the real Spanish notarial corpus page, imported through `format.import` the way a person
imports it: its lines carry the corpus's abbreviation markup (`dha$.dicha`), the case the levels exist
for, where a person's expanded reading of a line and the line as written are both true at once.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import (
    counting_by_kind,
    counting_by_kind_and_level,
    document_text,
    ordered_lines,
    readings_of_segment,
    working_pass,
)
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, ReadingChoice, Status
from fichero_server.models.readings import (
    BUILTIN_READING_LEVELS,
    LibraryReadingLevel,
    UnknownReadingLevel,
    assert_known_reading_level,
    canonical_reading_level,
    reading_levels,
)

pytestmark = pytest.mark.source_model

PAGE = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus" / "transkribus_spanish-notarial_0074.page.xml"
PERSON = ActionContext(actor="historian", library_path=None, is_bootstrap=True)


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


def _write(db, segment, content: str, **extra):
    return registry.invoke(db, "representation.create", {
        "document_id": segment.document_id, "segment_id": segment.id, "kind": "transcription",
        "content": content, **extra}, PERSON).result["id"]


def _counting_text(db, segment) -> str | None:
    items = readings_of_segment(db, segment.id)
    answer = counting_by_kind(db, segment.id, items).get("transcription")
    return next((i.content for i in items if answer is not None and i.id == answer.representation_id), None)


class TestFiveLevelsShip:
    def test_the_five_levels_are_seeded_when_a_library_opens(self, db):
        """WHY: a level outside the list is refused, so the list itself must be there from the first
        open: graphemic, as written, expanded, regularised (u/v, i/j, long s), modernised."""
        assert set(reading_levels(db)) == {key for key, _label in BUILTIN_READING_LEVELS} == {
            "graphemic", "as_written", "expanded", "regularised", "modernised"}
        assert all(row.builtin for row in db.query(LibraryReadingLevel))

    def test_an_unknown_level_is_refused_on_write_and_the_list_is_named(self, db, line):
        """WHY: unchecked, `diplomatic` and `as written` and `aswritten` were three levels nobody
        could count together. The refusal names the list so a caller can fix the call."""
        with pytest.raises(UnknownReadingLevel) as excinfo:
            _write(db, line, "hizieron donacion a la dicha Anna Maria su", level="diplomatik")
        assert "expanded" in str(excinfo.value) and "regularised" in str(excinfo.value)

    def test_a_project_can_add_a_level(self, db):
        """WHY: the list is open like the kinds list; a project's guideline may name its own."""
        db.save(LibraryReadingLevel(key="semi_diplomatic", label="Semi-diplomatic"))
        assert assert_known_reading_level(db, "semi-diplomatic") == "semi_diplomatic"


class TestOldSpellingsAreTheLevelsTheyMean:
    def test_the_recipes_as_written_with_a_hyphen_is_stored_as_as_written(self, db, line):
        """WHY: `recipe.yaml` and the app's setup sheet say `as-written`. Stored as sent, it would be a
        sixth level that never counts beside the line's other as-written readings."""
        rid = _write(db, line, "hizieron donacion a la dha Anna Maria su", level="as-written")
        assert db.get(ContentRepresentation, rid).level == "as_written"

    def test_normalised_is_regularised_and_an_old_row_is_never_rewritten(self, db, line):
        """WHY: `normalised` was the third shipped level. A stored row keeps it (nothing is migrated)
        and reads back as `regularised`; a new write under it is stored as `regularised`."""
        old = ContentRepresentation(document_id=line.document_id, segment_id=line.id, kind="transcription",
                                    content="hizieron donacion a la dicha Anna María su", level="normalised",
                                    source_anchor=line.anchor.model_copy())
        db.save(old)
        (read,) = [item for item in readings_of_segment(db, line.id) if item.id == old.id]
        assert read.level == "regularised"
        assert db.get(ContentRepresentation, old.id).level == "normalised"
        assert canonical_reading_level("Normalised") == "regularised"
        new = _write(db, line, "hizieron donacion a la dicha Anna María su", level="normalised")
        assert db.get(ContentRepresentation, new).level == "regularised"


class TestWhichReadingCountsIsPerKindAndLevel:
    def test_a_persons_expanded_reading_does_not_replace_the_line_as_written(self, db, line):
        """WHY (ruled 2026-10-10): counted per kind only, a person's expanded reading outranked the
        file's as-written one, and the page's text, its export and the Kraken set lost `dha`."""
        as_written = _counting_text(db, line)
        assert as_written is not None and "dha" in as_written
        opened = _write(db, line, "hizieron donacion a la dicha Anna Maria su", level="expanded")

        assert _counting_text(db, line) == as_written
        by_level = counting_by_kind_and_level(db, line.id, readings_of_segment(db, line.id))
        assert by_level[("transcription", "expanded")].representation_id == opened
        assert by_level[("transcription", "as_written")].representation_id != opened
        assert "dicha Anna" not in document_text(db, line.document_id).text

    def test_a_persons_as_written_correction_still_counts_over_the_files(self, db, line):
        """WHY: the levels split counting; they must not stop a correction at the same level counting."""
        fixed = _write(db, line, "hizieron donacion a la dha Anna Maria su", level="as_written")
        assert _counting_text(db, line) == "hizieron donacion a la dha Anna Maria su"
        assert counting_by_kind(db, line.id, readings_of_segment(db, line.id))["transcription"].representation_id == fixed

    def test_choosing_an_expanded_reading_leaves_the_as_written_choice_standing(self, db, line):
        """WHY: a choice superseded every earlier choice of its kind, so choosing which expansion counts
        silently undid a person's choice of what the line says as written."""
        written = _write(db, line, "hizieron donacion a la dha Anna Maria su", level="as_written")
        opened = _write(db, line, "hizieron donacion a la dicha Anna Maria su", level="expanded")
        for rid in (written, opened):
            registry.invoke(db, "reading.choose", {"segment_id": line.id, "kind": "transcription",
                                                   "representation_id": rid}, PERSON)
        live = {c.representation_id for c in db.query(ReadingChoice, segment_id=line.id) if c.superseded_at is None}
        assert live == {written, opened}
        assert _counting_text(db, line) == "hizieron donacion a la dha Anna Maria su"

    def test_writing_an_expanded_reading_is_not_stale_against_the_as_written_one(self, db, line):
        """WHY: the compare-and-set names the reading that counted when the writer read; at another
        level, a reading counting at as-written is not the one the writer's expansion competes with."""
        _write(db, line, "hizieron donacion a la dha Anna Maria su", level="as_written")
        first = _write(db, line, "hizieron donacion a la dicha Anna Maria su", level="expanded")
        second = _write(db, line, "hizieron donacion á la dicha Anna Maria su", level="expanded",
                        expected_counting_id=first)
        assert db.get(ContentRepresentation, second).level == "expanded"
