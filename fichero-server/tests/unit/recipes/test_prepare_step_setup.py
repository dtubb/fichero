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
