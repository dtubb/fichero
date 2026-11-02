"""`designer.how.what-to-check` (#6052): the pages a reader is least sure of, at most five, least sure first."""
from __future__ import annotations

from fichero_server.llm.working_lines import write_readings
from fichero_server.models import Artifact, DocType, Document, Segment
from fichero_server.recipes import what_to_check
from tests.unit.training.test_kraken_training_set import _page, notebook  # noqa: F401  (the fixture)


def _read(db, tmp_path, notebook, name, confidences):  # noqa: F811
    (tmp_path / name).mkdir()
    page = _page(db, tmp_path / name, name, notebook)
    lines = sorted((s for s in db.query(Segment, document_id=page.id) if s.kind == "line" and not s.deleted_at), key=lambda s: s.id)
    art = Artifact(document_id=page.id, artifact_type="transcription", content="x", model="m")
    db.save(art)
    write_readings(db, document_id=page.id, readings=[(line.id, "x", c) for line, c in zip(lines, confidences)],
                   artifact_id=art.id, run_id="r", level="as_written")
    return page.id


def test_the_least_sure_pages_come_first_and_at_most_five(db, tmp_path, notebook):  # noqa: F811
    ids = [_read(db, tmp_path, notebook, f"p{i}", [0.2 + i * 0.1] * 99) for i in range(7)]
    got = what_to_check.least_sure(db, ids)
    assert [g["page_id"] for g in got] == ids[:5]
    assert got[0]["certainty"] < got[1]["certainty"] and got[0]["lines_unsure"] == got[0]["lines"] > 0


def test_a_page_with_no_certainty_is_never_named(db, tmp_path, notebook):  # noqa: F811
    sure_less = _read(db, tmp_path, notebook, "a", [0.4] * 99)
    none = Document(name="b", doc_type=DocType.page)
    db.save(none)
    assert [g["page_id"] for g in what_to_check.least_sure(db, [sure_less, none.id])] == [sure_less]
    assert what_to_check.least_sure(db, []) == []
