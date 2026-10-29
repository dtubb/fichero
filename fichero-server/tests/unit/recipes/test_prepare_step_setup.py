"""The Prepare Images step runs the page operations from the Start plan (`prep.setup.step-runs-from-the-start-plan`, #5580)."""
from __future__ import annotations

from fichero_server.models import DocType, Document, FileType
from tests.unit.media.test_turn_straighten_blank import _graph_paper


def test_the_prepare_card_finds_the_page_and_hides_a_blank_one(db, tmp_path):
    from fichero_server.recipes.runner import _run_prepare

    ids = []
    for name, ink in (("blank.png", False), ("written.png", True)):
        path = tmp_path / name
        _graph_paper(ink=ink).save(path)
        doc = Document(name=name, doc_type=DocType.page, file_type=FileType.image, path=str(path), metadata={})
        db.save(doc)
        ids.append(doc.id)
    step: dict = {}

    child, state, why = _run_prepare(db, ids, "run-1", step)

    assert (child, state, why) == (None, "done", None)
    assert step["page_prep"]["blank"] == 1 and step["page_prep"]["pages"] == 2
    assert db.get(Document, ids[0]).exclude_from_processing is True
    assert "prepared" in step


def test_a_ruled_page_with_three_strokes_is_kept_and_proposed_not_hidden(db, tmp_path):
    """`prep.blank-pages-marked`: hidden only when sure; unsure stores a proposal and the page still goes on."""
    from fichero_server.recipes.page_crop import crop_pages
    from tests.unit.media.test_turn_straighten_blank import _ledger_with_strokes

    ids = []
    for name, strokes in (("empty.png", 0), ("strokes.png", 3)):
        path = tmp_path / name
        _ledger_with_strokes(strokes).save(path)
        doc = Document(name=name, doc_type=DocType.page, file_type=FileType.image, path=str(path), metadata={})
        db.save(doc)
        ids.append(doc.id)

    account = crop_pages(db, ids, "run-2", prepare=True)

    assert account["blank"] == 1
    assert db.get(Document, ids[0]).exclude_from_processing is True
    kept = db.get(Document, ids[1])
    assert not kept.exclude_from_processing
    assert "blank" in (kept.metadata or {}).get("prep_proposals", {})
