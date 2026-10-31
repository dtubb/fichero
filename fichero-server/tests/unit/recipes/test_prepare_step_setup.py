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


# --- `wide.prepare.plan-runs-only-chosen-operations` (#5382, #5580): the plan's card and the run follow the operations ---

PREP = {"id": "prep", "job": "prepare-the-image", "model": {"builtin": "image-preparer"}}
LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}, "runs_on": "this-mac"}
SPLIT = {"id": "split", "job": "split-pages", "model": {"builtin": "page-splitter"}}


def _recipe(*steps):
    return {"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t", "steps": list(steps)}


def _plan(recipe, **job_answers):
    from fichero_server.recipes.start import plan_start

    return plan_start(recipe, stays_local=True, job_answers=job_answers)


def _prepare_run(plan):
    return next((r for r in plan["runs"] if r["card"] == "prepare"), None)


def test_wide_the_prepare_card_carries_the_operations_the_questions_default_to():
    """No hand choice: crop and straighten, and clarity where the paper answer allows it (none: it looks at each page)."""
    assert _prepare_run(_plan(_recipe(PREP)))["operations"] == ["straighten", "crop", "clarity"]
    assert _prepare_run(_plan(_recipe(PREP), the_paper=["ruled"]))["operations"] == ["straighten", "crop"]
    assert _prepare_run(_plan(_recipe(PREP), the_paper=["faded"]))["operations"] == ["straighten", "crop", "clarity"]


def test_wide_the_card_runs_exactly_the_operations_the_hand_chose():
    run = _prepare_run(_plan(_recipe(PREP), prepare_operations=["crop"]))
    assert run["operations"] == ["crop"]
    assert _prepare_run(_plan(_recipe(PREP), prepare_operations=["clarity"], the_paper=["ruled"]))["operations"] == ["clarity"]


def test_wide_every_operation_off_is_a_plan_with_no_prepare_run_and_says_so():
    plan = _plan(_recipe(PREP, LINES), prepare_operations=[])
    assert _prepare_run(plan) is None
    (said,) = [s for s in plan["skipped"] if s["step"] == "prep"]
    assert "switched off" in said["why"], said
    only_split = _plan(_recipe(PREP, SPLIT), prepare_operations=["split"])
    assert _prepare_run(only_split) is None and [r["job"] for r in only_split["runs"]] == ["split-pages"]


def test_wide_split_off_takes_the_split_job_out_of_the_plan_as_the_explicit_no_does():
    kept = _plan(_recipe(SPLIT, PREP), prepare_operations=["split", "crop"])
    assert [r["job"] for r in kept["runs"]] == ["split-pages", "prepare-the-image"]
    off = _plan(_recipe(SPLIT, PREP), prepare_operations=["crop"])
    assert [r["job"] for r in off["runs"]] == ["prepare-the-image"]
    assert any(s["step"] == "split" and "not cut" in s["why"] for s in off["skipped"])
    # the hand's yes wins over the question's no
    yes = _plan(_recipe(SPLIT, PREP), prepare_operations=["split", "crop"], two_pages_per_image=False)
    assert "split-pages" in [r["job"] for r in yes["runs"]]


def _flat_pages(db, tmp_path, monkeypatch, upside_down=True):
    """A flat 3-degree scan the finder cannot outline, read upside down: turn, straighten and crop each have something to do."""
    from fichero_server.media import find_page as module
    from fichero_server.media import turn_by_text as turn_module
    from tests.unit.media.test_turn_straighten_blank import _flat_scan, _lines_of

    monkeypatch.setattr(module, "find_page", lambda image: None)
    monkeypatch.setattr(turn_module, "read_lines", lambda image, db_path=None: _lines_of(180 if upside_down else 0))
    doc = _flat_scan(tmp_path)
    db.save(doc)
    return doc


def _roles(db, doc):
    from fichero_server.models import Rendition

    return {r.role for r in db.query(Rendition, document_id=doc.id)}


def test_wide_run_straighten_alone_turns_and_straightens_and_finds_no_page(db, tmp_path, monkeypatch):
    from fichero_server.recipes.prepare_run import run_prepare

    doc = _flat_pages(db, tmp_path, monkeypatch)
    step: dict = {}
    run_prepare(db, [doc.id], "run-1", step, operations=["straighten"])
    assert _roles(db, doc) == {"rotated", "deskewed"} and "prepared" not in step
    assert (db.get(Document, doc.id).metadata or {}).get("page_box") is None


def test_wide_run_crop_alone_finds_the_page_and_leaves_the_turn_alone(db, tmp_path, monkeypatch):
    from fichero_server.media import find_page as module
    from fichero_server.recipes.prepare_run import run_prepare
    from tests.unit.media.test_turn_straighten_blank import _lines_of, _ruled
    from fichero_server.media import turn_by_text as turn_module
    from PIL import Image

    table = Image.new("RGB", (1400, 1100), (14, 12, 10))
    table.paste(_ruled(2.0).resize((900, 700)), (250, 200))
    path = tmp_path / "photo.png"
    table.save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    monkeypatch.setattr(module, "find_page_vision", lambda image: None)
    monkeypatch.setattr(turn_module, "read_lines", lambda image, db_path=None: _lines_of(180))
    step: dict = {}
    run_prepare(db, [doc.id], "run-1", step, operations=["crop"])
    roles = _roles(db, doc)
    assert "crop" in roles and not roles & {"rotated", "deskewed"}, roles
    assert step["page_prep"]["cropped"] == 1


def test_wide_run_clarity_alone_runs_no_page_operation(db, tmp_path, monkeypatch):
    from fichero_server.recipes.prepare_run import run_prepare

    doc = _flat_pages(db, tmp_path, monkeypatch)
    step: dict = {}
    run_prepare(db, [doc.id], "run-1", step, operations=["clarity"])
    assert "page_prep" not in step and "prepared" in step and _roles(db, doc) <= {"prepared"}


def test_wide_run_with_no_operations_given_runs_what_the_paper_answer_did_before(db, tmp_path, monkeypatch):
    """A `prepare` card from before the operations existed carries none: it runs as it did."""
    from fichero_server.recipes.prepare_run import run_prepare

    doc = _flat_pages(db, tmp_path, monkeypatch)
    step: dict = {}
    run_prepare(db, [doc.id], "run-1", step, paper=["ruled"])
    assert "page_prep" in step and "prepared" not in step and "rotated" in _roles(db, doc)


def test_wide_changing_the_operations_prepares_the_page_again(db, tmp_path, monkeypatch):
    """The stamp holds the operations: the same page under other operations is not `unchanged`."""
    from fichero_server.recipes.prepare_run import run_prepare

    doc = _flat_pages(db, tmp_path, monkeypatch)
    run_prepare(db, [doc.id], "run-1", {}, operations=["straighten"])
    same: dict = {}
    run_prepare(db, [doc.id], "run-2", same, operations=["straighten"])
    assert same["page_prep"]["unchanged"] == 1
    other: dict = {}
    run_prepare(db, [doc.id], "run-3", other, operations=["straighten", "crop"])
    assert other["page_prep"]["unchanged"] == 0 and other["page_prep"]["pages"] == 1
