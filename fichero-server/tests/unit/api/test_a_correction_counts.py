"""A person's correction counts over the reading it corrects (#5175).

WHY: `representation.create` with `corrects_representation_id` is what typing in the Reader
sends (#5154). When the corrected reading was a person's too -- an import stamped `human` before
#5150, or a colleague's transcription -- the two were EQUAL ALTERNATIVES, and in a strict project
nothing counted: the line's text vanished from the page the moment somebody fixed a typo. A
correction is not a rival reading; it is a judgement ABOUT the one it names. If this regresses,
every correction typed in the Reader blanks its line; if the rule widens, two historians'
independent readings stop being equal alternatives, or a machine's "correction" overrules a
person.

Through `format.import` of a real page; the line's text is checked against the file (lxml).
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import counting_by_kind, document_text, readings_of_segment
from tests.unit.api.test_page_text_follows_the_file import BOOT
from tests.unit.api.test_reader_directions import ARABIC, _import, _line_texts
from tests.unit.api.test_reader_line_map import _view

OTHER = ActionContext(actor="colleague", library_path=None, is_bootstrap=True)


def _third_line(db, client):
    doc_id = _import(db, ARABIC)
    line = _view(client, doc_id)[0]["pages"][0]["lines"][2]
    return doc_id, line["segment_id"], line["representation_id"]


def _write(db, doc_id, segment_id, content, corrects=None, ctx=BOOT):
    return registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": segment_id, "kind": "transcription",
        "content": content, "corrects_representation_id": corrects,
    }, ctx)


def _counts(db, segment_id):
    return counting_by_kind(db, segment_id, readings_of_segment(db, segment_id))["transcription"]


def test_a_correction_of_the_files_reading_counts_and_shows_once(db, client):
    doc_id, segment_id, file_reading = _third_line(db, client)
    original = [t for t in _line_texts(ARABIC) if t][2]
    corrected = original + " ✓"
    fix = _write(db, doc_id, segment_id, corrected, corrects=file_reading).result["id"]
    answer = _counts(db, segment_id)
    assert (answer.representation_id, answer.basis.value) == (fix, "correction")
    text = document_text(db, doc_id).text
    assert text.count(corrected) == 1 and (original + " ") not in text.replace(corrected, "")


def test_a_correction_of_a_persons_reading_does_not_blank_the_line(db, client):
    """THE #5175 CASE: both readings a person's. Before, equal alternatives -- nothing counted."""
    doc_id, segment_id, _file = _third_line(db, client)
    theirs = _write(db, doc_id, segment_id, "a colleague's reading", ctx=OTHER).result["id"]
    fix = _write(db, doc_id, segment_id, "my correction of it", corrects=theirs).result["id"]
    assert _counts(db, segment_id).representation_id == fix
    assert "my correction of it" in document_text(db, doc_id).text


def test_the_last_correction_in_a_chain_wins(db, client):
    doc_id, segment_id, file_reading = _third_line(db, client)
    first = _write(db, doc_id, segment_id, "first fix", corrects=file_reading).result["id"]
    second = _write(db, doc_id, segment_id, "second fix", corrects=first, ctx=OTHER).result["id"]
    assert (_counts(db, segment_id).representation_id, _counts(db, segment_id).basis.value) == (second, "correction")


def test_undoing_the_correction_brings_the_files_reading_back(db, client):
    doc_id, segment_id, file_reading = _third_line(db, client)
    audit_id = _write(db, doc_id, segment_id, "a fix", corrects=file_reading).audit_id
    assert client.post(f"/api/actions/audit/{audit_id}/undo").status_code == 200
    assert _counts(db, segment_id).representation_id == file_reading


def test_independent_readings_are_still_equal_alternatives(db, client):
    doc_id, segment_id, _file = _third_line(db, client)
    _write(db, doc_id, segment_id, "one reading")
    _write(db, doc_id, segment_id, "another reading", ctx=OTHER)
    assert _counts(db, segment_id).representation_id is None


def test_a_choice_still_overrides_a_correction(db, client):
    doc_id, segment_id, file_reading = _third_line(db, client)
    _write(db, doc_id, segment_id, "a fix", corrects=file_reading)
    registry.invoke(db, "reading.choose", {
        "segment_id": segment_id, "kind": "transcription", "representation_id": file_reading}, BOOT)
    assert (_counts(db, segment_id).representation_id, _counts(db, segment_id).basis.value) == (file_reading, "chosen")
