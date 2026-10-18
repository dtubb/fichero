"""`source.train.on-the-persons-corrections` (#5700): the line reader's train offer fine-tunes on the lines a person
corrected (teacher `person`), the material its readiness counts; distilling a model's lines stays a second way.

WHY: the offer counted corrected lines ("Needs 2,000 corrected lines") but trained on a model's readings.
"""
from __future__ import annotations

from fichero_server.recipes.train_offers import due_starts, train_offers

RECIPE = {"steps": [{"id": "read", "job": "read-a-line", "settings": {}}]}
COUNTS = {"pages": [{"lines": 3000}] * 20, "unmarked": 0, "region_pages": 0, "scope_ids": ["root"], "teacher": None}
HERE = {"mode": "here", "why": ""}


def test_the_first_way_fine_tunes_on_the_persons_corrected_lines_5700():
    (offer,) = train_offers(RECIPE, COUNTS, stays_local=True, setting=HERE)
    first = offer["ways"][0]
    assert first["how"] == "fine-tune" and "corrected" in first["says"]
    assert first["targets"][0]["params"] == {"scope_ids": ["root"], "teacher": "person"}


def test_under_here_the_persons_lines_are_what_trains_even_with_no_model_teacher_5700():
    (offer,) = train_offers(RECIPE, COUNTS, stays_local=True, setting=HERE)
    assert due_starts([offer]) == [("training.start_here", {"scope_ids": ["root"], "teacher": "person"})]


def test_distilling_a_models_lines_is_still_offered_with_its_teacher_5700():
    (offer,) = train_offers(RECIPE, {**COUNTS, "teacher": "gemini-2.5-pro"}, stays_local=False, setting=HERE)
    distil = [w for w in offer["ways"] if w["how"] == "distil" and w["method"] == "kraken"]
    assert distil and distil[0]["targets"][0]["params"]["teacher"] == "gemini-2.5-pro"


def test_the_readiness_count_is_the_set_it_trains_on_5700(client, db, tmp_path):
    """The offer's corrected-line count (`_corrected_lines`, the bake-off's one rule) is the number of lines the
    person's set holds, so "N of 2,000 corrected lines" is what the reader learns from."""
    from fichero_server.models import DocType, Document, Segment
    from fichero_server.recipes.train_offers import _corrected_lines
    from fichero_server.training.kraken_set import PERSON, export_training_set
    from tests.unit.training.test_kraken_training_set import _page

    folder = Document(name="SM_NPQ_C09", doc_type=DocType.folder)
    db.save(folder)
    page = _page(db, tmp_path, "SM_NPQ_C09_001", folder)
    lines = sorted((s for s in db.query(Segment, document_id=page.id) if s.kind == "line" and not s.deleted_at),
                   key=lambda s: s.id)
    for segment, text in zip(lines[:2], ("primera linea corregida", "segunda linea corregida"), strict=True):
        assert client.post(f"/api/segments/{segment.id}/correct", json={"text": text}).status_code == 200
    made = export_training_set(db, scope_ids=[folder.id], teacher=PERSON, held_out_ids=[], out_dir=tmp_path / "set")
    assert made.lines == _corrected_lines(db) == 2


def test_a_reader_taught_by_the_persons_corrections_says_so_on_its_card_5700():
    """A card never says "taught by person … none checked by a person" of the person's own lines."""
    from fichero_server.training.job import lessons, taught_by

    assert taught_by("person") == "your corrections" and taught_by("gemini") == "gemini"
    assert lessons("person", {"pages": 1, "lines": 2}) == "Trained on 1 page (2 lines you corrected)"
    assert "none checked by a person" in lessons("gemini", {"pages": 3, "lines": 9})
