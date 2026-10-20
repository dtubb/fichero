"""`source.compare.pick-is-a-training-line` (#5900): a line whose counting reading a person CHOSE among machine readings is a
line a person checked, so the person's Kraken set takes it; its manifest counts chosen and typed apart, both as the person's;
and a bake-off row for the same line is dropped before staging (one `line_key`), so the line is counted once, as the person's."""
from __future__ import annotations

import json

from fichero_server.models import ContentRepresentation, Segment
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.training import bakeoff_lines as bl
from fichero_server.training.kraken_set import MANIFEST, PERSON, build_training_set, export_training_set
from tests.unit.training.test_kraken_training_set import _page, notebook  # noqa: F401  (the fixture)


def _lines(db, doc):
    return sorted((s for s in db.query(Segment, document_id=doc.id) if s.kind == "line" and not s.deleted_at),
                  key=lambda s: s.id)


def _another_machine_reading(db, segment, text):
    row = ContentRepresentation(document_id=segment.document_id, segment_id=segment.id, kind="transcription",
                                content=text, source_anchor=segment.anchor, producer_model="another-reader",
                                producer_run_id="run-b", provenance_kind=ProvenanceKind.workflow)
    db.save(row)
    return row


def test_a_pick_is_in_the_persons_training_set_and_a_model_reading_is_not(client, db, tmp_path, notebook):  # noqa: F811
    page = _page(db, tmp_path, "SM_NPQ_C09_001", notebook)
    typed, chosen = _lines(db, page)[:2]
    assert client.post(f"/api/segments/{typed.id}/correct", json={"text": "escrita por la persona"}).status_code == 200
    other = _another_machine_reading(db, chosen, "elegida entre dos lecturas")
    r = client.post(f"/api/segments/{chosen.id}/readings/choice", json={"kind": "transcription", "representation_id": other.id})
    assert r.status_code == 200, r.text

    out = tmp_path / "set"
    made = export_training_set(db, scope_ids=[notebook.id], teacher=PERSON, held_out_ids=[], out_dir=out)

    xml = (out / made.pages[0].xml).read_text(encoding="utf-8")
    assert "escrita por la persona" in xml and "elegida entre dos lecturas" in xml
    manifest = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
    assert (manifest["lines_typed_by_a_person"], manifest["lines_chosen_by_a_person"]) == (1, 1)
    assert manifest["lines_checked_by_a_person"] == 2 and manifest["lines_read_by_a_model"] == 0
    assert manifest["left_out"]["not_by_a_person"] == len(_lines(db, page)) - 2


def test_a_line_in_both_sets_is_counted_once_as_the_persons(client, db, tmp_path, notebook):  # noqa: F811
    from fichero_server.training.line_pairs import lines_with_ids

    page = _page(db, tmp_path, "SM_NPQ_C09_001", notebook)
    [first, *_rest] = _lines(db, page)
    assert client.post(f"/api/segments/{first.id}/correct", json={"text": "la persona"}).status_code == 200
    made = build_training_set(db, scope_ids=[notebook.id], teacher=PERSON, held_out_ids=[], out_dir=tmp_path / "set")
    assert len(made.line_keys) == made.lines == 1

    xml = (tmp_path / "set" / made.pages[0].xml).read_text(encoding="utf-8")
    [(_id, polygon, _text)] = lines_with_ids(xml)
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "p.png").write_bytes((tmp_path / "set" / made.pages[0].image).read_bytes())
    same = bl.WinningLine(page="p.png", line_id="0", polygon=[list(p) for p in polygon], text="un modelo", read_by="m", agreed_by=["a"])
    other = bl.WinningLine(page="p.png", line_id="1", polygon=[[0, 0], [10, 0], [10, 10]], text="otra linea", read_by="m", agreed_by=["a"])

    kept = bl.drop_lines_a_person_checked(bl.Winning([same, other], {}), pages, made.line_keys)

    assert [line.line_id for line in kept.lines] == ["1"]
    assert kept.left_out["also_a_persons_line"] == 1


def test_staging_drops_the_lines_a_person_already_checked_and_says_so(tmp_path):
    """The caller of the dedupe is `stage_dataset` itself: with the person's keys it stages the rest and counts the drop."""
    from fichero_server.training.line_key import image_digest, line_key
    from tests.unit.training.test_bakeoff_dataset_5894 import _lines_json, _pages

    pages = _pages(tmp_path)
    winning = bl.winning_lines(_lines_json(tmp_path), winner="mlx:m")
    assert [w.line_id for w in winning.lines] == ["0"]
    keys = {line_key(image_digest(pages / "p0.png"), winning.lines[0].polygon)}

    staged = bl.stage_dataset(winning, pages, tmp_path / "out", person_keys=keys)

    assert staged.count == 0
    assert '"also_a_persons_line": 1' in (tmp_path / "out" / "README.md").read_text(encoding="utf-8")
    kept = bl.stage_dataset(winning, pages, tmp_path / "out2", person_keys={"not-this-line"})
    assert kept.count == 1


# --- the pick is `reading.choose`, with a compare-and-set (`source.compare.pick`) ---------------------------------

import pytest  # noqa: E402

from fichero_server.actions.registry import ActionContext, registry  # noqa: E402
from fichero_server.models.readings import ChoiceNeedsAPerson, ReadingChoice  # noqa: E402
from tests.unit.api.test_segment_readings import (  # noqa: E402,F401
    _artifact, _convert, _converted_segments, _make_doc, _person, _write,
)


def _two_readings(db, client):
    doc = _make_doc(db)
    artifact = _artifact(db, doc)
    _convert(client, artifact.id)
    segment = _converted_segments(db, artifact.id)[1]
    first = _write(db, segment, content="nombre").result["id"]
    second = _write(db, segment, content="nomine").result["id"]
    return segment, first, second


def _counting(client, segment):
    return client.get(f"/api/segments/{segment.id}/readings?kind=transcription").json()["counting"]["transcription"]["representation_id"]


def test_a_pick_on_the_view_the_person_saw_is_recorded(db, client):
    segment, first, second = _two_readings(db, client)
    saw = _counting(client, segment)
    pick = first if saw != first else second
    r = client.post(f"/api/segments/{segment.id}/readings/choice",
                    json={"kind": "transcription", "representation_id": pick, "expected_counting_id": saw})
    assert r.status_code == 200, r.text
    assert _counting(client, segment) == pick


def test_a_pick_on_a_stale_view_is_refused_with_409_and_writes_nothing(db, client):
    segment, first, second = _two_readings(db, client)
    counting = _counting(client, segment)
    other = first if counting != first else second
    # the view said `other` counted; in fact `counting` does
    r = client.post(f"/api/segments/{segment.id}/readings/choice",
                    json={"kind": "transcription", "representation_id": other, "expected_counting_id": other})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["counting_representation_id"] == counting
    assert not list(db.query(ReadingChoice, segment_id=segment.id)), "a refused pick writes no choice"
    assert _counting(client, segment) == counting


def test_a_model_may_not_pick_even_with_a_matching_view(db, client):
    segment, first, second = _two_readings(db, client)
    with pytest.raises(ChoiceNeedsAPerson):
        registry.invoke(db, "reading.choose",
                        {"segment_id": segment.id, "kind": "transcription", "representation_id": first,
                         "expected_counting_id": second},
                        ActionContext(actor="runner", run_id="run-1", is_bootstrap=True))


def test_one_undo_takes_a_pick_back(db, client):
    segment, first, second = _two_readings(db, client)
    before = _counting(client, segment)
    pick = first if before != first else second
    done = registry.invoke(db, "reading.choose",
                           {"segment_id": segment.id, "kind": "transcription", "representation_id": pick,
                            "expected_counting_id": before}, _person())
    assert _counting(client, segment) == pick
    assert client.post(f"/api/actions/audit/{done.id}/undo").status_code == 200
    assert _counting(client, segment) == before
