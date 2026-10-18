"""`source.train.on-the-persons-corrections` (#5700): a set whose lessons are the lines a PERSON corrected, not only a
model's readings. The teacher named `person` is that set: for each page, the lines whose counting reading a person
made (a correction, `POST /api/segments/{id}/correct`); the rest are left out and counted, so the readiness count and
the set are the same lines."""
from __future__ import annotations

import json

from fichero_server.models import Segment
from fichero_server.training.kraken_set import MANIFEST, PERSON, EmptyTrainingSet, build_training_set, export_training_set
from tests.unit.training.test_kraken_training_set import _page, notebook  # noqa: F401  (the fixture)

import pytest


def _lines(db, doc):
    return sorted((s for s in db.query(Segment, document_id=doc.id) if s.kind == "line" and not s.deleted_at),
                  key=lambda s: s.id)


def test_the_set_holds_only_the_lines_a_person_corrected(client, db, tmp_path, notebook):  # noqa: F811
    """WHY: Kraken fine-tuned on a model's own lines learns the model's mistakes; the person's corrections are the
    only ground truth. A line nobody corrected must stay out, and the manifest must say a person checked these."""
    page = _page(db, tmp_path, "SM_NPQ_C09_001", notebook)
    lines = _lines(db, page)
    assert len(lines) > 2
    for segment, text in zip(lines[:2], ("primera linea corregida", "segunda linea corregida"), strict=True):
        r = client.post(f"/api/segments/{segment.id}/correct", json={"text": text})
        assert r.status_code == 200, r.text

    out = tmp_path / "set"
    made = export_training_set(db, scope_ids=[notebook.id], teacher=PERSON, held_out_ids=[], out_dir=out)

    assert made.lines == 2
    xml = (out / made.pages[0].xml).read_text(encoding="utf-8")
    assert "primera linea corregida" in xml and "segunda linea corregida" in xml
    manifest = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["lines_checked_by_a_person"] == 2 and manifest["lines_read_by_a_model"] == 0
    assert manifest["left_out"]["not_by_a_person"] == len(lines) - 2


def test_a_page_nobody_corrected_is_listed_with_why(db, tmp_path, notebook):  # noqa: F811
    """WHY: the start refuses an empty set with the preview's reason; 'no pass read by person' sent the operator
    looking for a pass that never existed (the 2026-10-11 walk)."""
    page = _page(db, tmp_path, "SM_NPQ_C09_001", notebook)
    made = build_training_set(db, scope_ids=[notebook.id], teacher=PERSON, held_out_ids=[], out_dir=None)
    assert made.pages == [] and made.missing[0]["document_id"] == page.id
    assert "corrected by a person" in made.missing[0]["why"]
    with pytest.raises(EmptyTrainingSet):
        export_training_set(db, scope_ids=[notebook.id], teacher=PERSON, held_out_ids=[], out_dir=tmp_path / "x")

