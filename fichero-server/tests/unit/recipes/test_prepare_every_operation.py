"""The recipe designer's Prepare Images card offers every image operation, off unless the hand switches it on
(`image.ops.recipe-designer-offers-every-operation`, #6363)."""
from __future__ import annotations

from PIL import Image

from fichero_server.recipes import prepare_operations as ops
from fichero_server.models import Document, FileType
from tests.unit.recipes.test_prepare_step_setup import PREP, _plan, _prepare_run, _recipe


def test_the_suite_is_offered_in_order_each_with_a_sentence_and_off_by_default():
    listed = ops.listing(None)
    assert [o["id"] for o in listed][:4] == ["split", "straighten", "crop", "clarity"]  # today's four stay first, as they were
    extra = [o for o in listed if o["id"] in ops.EXTRA]
    assert [o["id"] for o in extra] == list(ops.EXTRA) and {"flip", "binarise", "grayscale"} <= set(ops.EXTRA)
    assert all(o["sentence"] and not o["on"] and not o["default"] for o in extra)


def test_a_hand_that_picks_flip_and_binarise_runs_those_two_in_suite_order():
    assert ops.to_run({ops.ANSWER: ["flip", "binarise"]}) == ["binarise", "flip"]
    assert _prepare_run(_plan(_recipe(PREP), prepare_operations=["flip", "binarise"]))["operations"] == ["binarise", "flip"]


def test_a_hand_that_picks_nothing_runs_the_four_defaults_as_today():
    assert _prepare_run(_plan(_recipe(PREP)))["operations"] == ["straighten", "crop", "clarity"]


def test_the_plans_sentence_names_the_extra_operations():
    how = _prepare_run(_plan(_recipe(PREP), prepare_operations=["flip", "binarise"]))["how"]
    assert "Flip" in how and "Binarise" in how
    assert "Flip" not in _prepare_run(_plan(_recipe(PREP)))["how"]


def _page(db, tmp_path):
    path = tmp_path / "p.png"
    Image.new("RGB", (80, 60), (200, 190, 170)).save(path)
    doc = Document(name="p.png", path=str(path), file_type=FileType.image)
    db.save(doc)
    return doc


def test_the_run_executes_each_pick_through_its_audited_action_and_undo_takes_it_back(db, tmp_path):
    import asyncio

    from fichero_server.actions.registry import ActionContext
    from fichero_server.api.routes.system.actions_registry import undo_action
    from fichero_server.models import ActionAudit, ImageEditChain
    from fichero_server.recipes.prepare_run import run_prepare

    doc = _page(db, tmp_path)
    step: dict = {}
    run_prepare(db, [doc.id], "run-1", step, operations=["binarise", "flip"])
    chain = list(db.query(ImageEditChain, document_id=doc.id))[0]
    assert [o["op"] for o in chain.operations] == ["binarise", "flip_horizontal"]
    audits = [a for a in db.query(ActionAudit) if a.action_name in ("image.binarise", "image.flip_horizontal")]
    assert sorted(a.action_name for a in audits) == ["image.binarise", "image.flip_horizontal"]  # one entry each
    assert step["extra_operations"]["ran"] == 2
    run_prepare(db, [doc.id], "run-2", {}, operations=["binarise", "flip"])  # a second run leaves what the first did
    assert len(list(db.query(ImageEditChain, document_id=doc.id))[0].operations) == 2
    last = next(a for a in audits if a.action_name == "image.flip_horizontal")
    asyncio.run(undo_action(last.id, request=None, db=db, ctx=ActionContext(actor="person", library_path=str(db.path.parent)),
                            x_fichero_library_path=str(db.path.parent), x_fichero_origin_window=None))
    assert len(list(db.query(ImageEditChain, document_id=doc.id))[0].operations) == 1
