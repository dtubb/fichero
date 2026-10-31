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


def test_an_unhidden_page_goes_through_the_steps_it_skipped(db, tmp_path):
    """`prep.check.blank-mark-is-a-correction`: unhiding queues the page; its page box is found."""
    from fichero_server.media.blank_page import mark_blank
    from fichero_server.api.routes.ingest.image_editing import mark_blank_impl

    path = tmp_path / "p.png"
    _graph_paper(ink=True).save(path)
    doc = Document(name="p.png", doc_type=DocType.page, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    mark_blank(db, doc.id, True, who="person")
    mark_blank_impl(db, doc.id, False)
    assert not db.get(Document, doc.id).exclude_from_processing
    assert db.get(Document, doc.id).metadata.get("blank", {}).get("blank") is False


def test_the_paper_answer_gates_the_contrast_step_and_the_facts_suggest_from_the_sample(db, tmp_path):
    from fichero_server.recipes.prepare_suggest import estimate, sample_ids, suggest
    from fichero_server.recipes.runner import _run_prepare
    from fichero_server.recipes.stages import STAGES

    keys = [q.key for s in STAGES if s.id == "prepare-images" for q in s.questions]
    assert keys == ["two_pages_per_image", "beside_the_page", "the_paper", "check_missed_lines"]
    assert sample_ids([str(i) for i in range(20)]) == ["0", "5", "10", "15", "19"]
    ids = []
    for n in range(5):
        path = tmp_path / f"g{n}.png"
        _graph_paper(ink=True).save(path)
        doc = Document(name=path.name, doc_type=DocType.page, file_type=FileType.image, path=str(path), metadata={})
        db.save(doc)
        ids.append(doc.id)
    step: dict = {}
    _run_prepare(db, ids, "run-3", step, paper=["ruled"])
    assert "prepared" not in step  # not faded: the contrast step did not run
    got = suggest(db)
    assert got["the_paper"]["value"] == ["ruled"] and got["the_paper"]["agree"].endswith("of 5")
    assert "estimate" in estimate(374) and "2 min" in estimate(374)


def test_one_failing_page_is_skipped_and_the_step_still_prepares_the_rest(db, tmp_path, monkeypatch):
    """Review finding: any error but an unreadable image failed the step for every page and skipped the contrast step."""
    from fichero_server.media import find_page as module
    from fichero_server.recipes import page_crop
    from fichero_server.recipes.runner import _run_prepare

    ids = []
    for n in range(3):
        path = tmp_path / f"p{n}.png"
        _graph_paper(ink=True).save(path)
        doc = Document(name=path.name, doc_type=DocType.page, file_type=FileType.image, path=str(path), metadata={})
        db.save(doc)
        ids.append(doc.id)
    real = module.find_page

    def flaky(image, **kw):
        if flaky.calls == 1:
            flaky.calls += 1
            raise RuntimeError("probe: the finder broke on this page")
        flaky.calls += 1
        return real(image, **kw)

    flaky.calls = 0
    monkeypatch.setattr(page_crop, "find_page", flaky, raising=False)
    monkeypatch.setattr(module, "find_page", flaky)
    step: dict = {}

    child, state, _why = _run_prepare(db, ids, "run-9", step)

    assert state == "done"
    assert step["page_prep"]["pages"] == 3 and step["page_prep"].get("failed") == 1
    assert "prepared" in step, "the contrast step still ran"
