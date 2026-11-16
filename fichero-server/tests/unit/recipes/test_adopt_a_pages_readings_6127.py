"""`wide.try.start-reuses-a-matching-try`, slice B (#6127): a kept copy's readings land on the project's own matching lines, once, never over a
person's reading, and the done rule then counts the page for that model."""
from __future__ import annotations

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.llm.working_lines import write_readings
from fichero_server.models import Artifact, ContentRepresentation, DocType, Document, Segment
from fichero_server.recipes import adopt, done
from fichero_server.recipes.samples import _snapshot
from tests.unit.training.test_kraken_training_set import _page, notebook  # noqa: F401  (the fixture)


@pytest.fixture
def copy_db(tmp_path):
    scratch = tmp_path / "scratch.fichero"
    for sub in ("lance", "storage", "files"):
        (scratch / sub).mkdir(parents=True)
    yield db_manager.get_database(scratch)
    db_manager.close_database(scratch)


def _lines(db, doc):
    return sorted((s for s in db.query(Segment, document_id=doc.id) if s.kind == "line" and not s.deleted_at), key=lambda s: s.id)


def _tried(db, copy_db, tmp_path, notebook):  # noqa: F811
    (tmp_path / "a").mkdir(), (tmp_path / "b").mkdir()
    page = _page(db, tmp_path / "a", "P1", notebook)
    folder = Document(name="Samples", doc_type=DocType.folder)
    copy_db.save(folder)
    twin = _page(copy_db, tmp_path / "b", "P1", folder)
    snap = _snapshot(copy_db)
    art = Artifact(document_id=twin.id, artifact_type="transcription", content="hola", model="m")
    copy_db.save(art)
    first = _lines(copy_db, twin)[0]
    write_readings(copy_db, document_id=twin.id, readings=[(first.id, "hola", 0.9)], artifact_id=art.id, run_id="r", level="as_written")
    before = {k: sorted(v) for k, v in snap.items() if k in ("Artifact", "ContentRepresentation")}
    return page, {"page": page.id, "copy_page": twin.id}, before


def _adopt(db, copy_db, rec, before):
    return adopt.adopt_page(db, copy_db, rec, before, scratch_name="read", run_id="run-1", min_iou=0.9)


def test_the_tries_reading_lands_on_the_matching_project_line_and_the_page_counts_as_read_by_that_model(db, copy_db, tmp_path, notebook):  # noqa: F811
    page, rec, before = _tried(db, copy_db, tmp_path, notebook)
    assert not done._has_line_readings(db, page.id, "m")
    got = _adopt(db, copy_db, rec, before)
    assert got["readings"] == 1
    (reading,) = [r for r in db.query(ContentRepresentation, document_id=page.id) if r.content == "hola"]
    assert reading.segment_id in {s.id for s in _lines(db, page)} and reading.derived_from_artifact_id
    assert done._has_line_readings(db, page.id, "m")  # the existing done rule counts it: no new rule


def test_a_second_adoption_writes_nothing(db, copy_db, tmp_path, notebook):  # noqa: F811
    page, rec, before = _tried(db, copy_db, tmp_path, notebook)
    _adopt(db, copy_db, rec, before)
    assert _adopt(db, copy_db, rec, before)["readings"] == 0
    assert len([r for r in db.query(ContentRepresentation, document_id=page.id) if r.content == "hola"]) == 1


def test_a_line_a_person_read_is_left_alone(client, db, copy_db, tmp_path, notebook):  # noqa: F811
    page, rec, before = _tried(db, copy_db, tmp_path, notebook)
    twin_lines = _lines(copy_db, copy_db.get(Document, rec["copy_page"]))
    matched = adopt.match_lines(twin_lines[:1], _lines(db, page), 0.9)  # the project line the try's reading would land on
    mine = db.get(Segment, matched[twin_lines[0].id])
    assert client.post(f"/api/segments/{mine.id}/correct", json={"text": "la persona"}).status_code == 200
    got = _adopt(db, copy_db, rec, before)
    assert got["skipped_person"] == 1 and got["readings"] == 0


def test_a_copy_line_with_no_matching_project_line_is_counted_not_created(db, copy_db, tmp_path, notebook):  # noqa: F811
    page, rec, before = _tried(db, copy_db, tmp_path, notebook)
    got = adopt.adopt_page(db, copy_db, rec, before, scratch_name="read", run_id="r", min_iou=1.01)  # nothing can match
    assert got["unmatched"] == 1 and got["readings"] == 0 and len(_lines(db, page)) == len(_lines(db, page))


def test_overlap_is_one_for_the_same_box_zero_when_apart_and_each_line_is_used_once():
    from types import SimpleNamespace as N

    box = lambda i, x: N(id=i, bbox_x=x, bbox_y=0.0, bbox_w=0.5, bbox_h=0.1)  # noqa: E731
    assert adopt.overlap((0, 0, 1, 1), (0, 0, 1, 1)) == 1 and adopt.overlap((0, 0, 1, 1), (2, 2, 1, 1)) == 0
    assert adopt.match_lines([box("c1", 0.0), box("c2", 0.0)], [box("p1", 0.0)], 0.9) == {"c1": "p1"}


def _kept_try(db, tmp_path, notebook, monkeypatch, *, stage="read"):  # noqa: F811
    """A project whose `read` stage was tried: the kept copy lives where `samples` keeps it, the result file records what the try ran."""
    import json
    from pathlib import Path

    from fichero_server.recipes import samples

    library = Path(db.path).parent
    (tmp_path / "a").mkdir(), (tmp_path / "b").mkdir()
    page = _page(db, tmp_path / "a", "P1", notebook)
    scratch = samples._folder(library) / f"{stage}.fichero"
    for sub in ("lance", "storage", "files"):
        (scratch / sub).mkdir(parents=True)
    copy = db_manager.get_database(scratch)
    folder = Document(name="Samples", doc_type=DocType.folder)
    copy.save(folder)
    twin = _page(copy, tmp_path / "b", "P1", folder)
    snap = _snapshot(copy)
    art = Artifact(document_id=twin.id, artifact_type="transcription", content="hola", model="m")
    copy.save(art)
    write_readings(copy, document_id=twin.id, readings=[(_lines(copy, twin)[0].id, "hola", 0.9)], artifact_id=art.id, run_id="r", level="as_written")
    db_manager.close_database(scratch)
    cards = [{"card": "workflow"}]
    monkeypatch.setattr(samples, "_stage_plan", lambda *a, **k: {"runs": cards})
    rec = adopt.page_record(db, library, page.id, twin.id, card_ids=["workflow"], hash_=adopt.settings_hash(cards))
    record = {"stage": stage, "before": {k: sorted(v) for k, v in snap.items() if k in ("Artifact", "ContentRepresentation")}, "pages": [rec]}
    adopt.keep(scratch, record)
    samples._result_path(library, stage).write_text(json.dumps({"adoption": record}), encoding="utf-8")
    return page, record


def test_start_adopts_a_stage_whose_page_and_settings_are_unchanged_and_one_undo_puts_it_back(client, db, tmp_path, notebook, monkeypatch):  # noqa: F811
    page, _ = _kept_try(db, tmp_path, notebook, monkeypatch)
    from pathlib import Path

    from fichero_server.recipes import samples

    assert adopt.kept_stages(samples._folder(Path(db.path).parent)) == ["read"]
    done_ = client.post("/api/actions/invoke", json={"name": "try.adopt", "params": {"stage": "read"}})
    assert done_.status_code == 200, done_.text
    assert done_.json()["result"]["pages"] == 1 and done._has_line_readings(db, page.id, "m")
    undone = client.post(f"/api/actions/audit/{done_.json()['audit_id']}/undo")
    assert undone.status_code == 200, undone.text
    assert not [r for r in db.query(ContentRepresentation, document_id=page.id) if r.content == "hola" and not r.retracted_at]


def test_a_page_changed_since_the_try_is_left_to_run_and_named(db, tmp_path, notebook, monkeypatch):  # noqa: F811
    from fichero_server.recipes import samples

    page, record = _kept_try(db, tmp_path, notebook, monkeypatch)
    monkeypatch.setattr(samples, "_stage_plan", lambda *a, **k: {"runs": [{"card": "another"}]})  # the step's settings changed
    got = adopt.adopt_stage(db, "read", run_id="start")
    assert got["pages"] == 0 and got["left_to_run"][0]["page"] == page.id and "settings changed" in got["left_to_run"][0]["why"]
    assert not done._has_line_readings(db, page.id, "m")
