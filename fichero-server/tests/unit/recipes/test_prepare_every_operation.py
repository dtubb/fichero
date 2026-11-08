"""The recipe designer's Prepare Images card offers every image operation, off unless the hand switches it on
(`image.ops.recipe-designer-offers-every-operation`, #6363)."""
from __future__ import annotations

from PIL import Image

from fichero_server.recipes import prepare_operations as ops
from fichero_server.models import Document, FileType, Rendition
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


def test_the_run_writes_one_enhanced_rendition_with_a_steps_row_for_each(db, tmp_path):
    from fichero_server.recipes.prepare_run import run_prepare

    path = tmp_path / "p.png"
    Image.new("RGB", (80, 60), (200, 190, 170)).save(path)
    doc = Document(name="p.png", path=str(path), file_type=FileType.image)
    db.save(doc)
    step: dict = {}
    run_prepare(db, [doc.id], "run-1", step, operations=["binarise", "flip"])
    enhanced = [r for r in db.query(Rendition, document_id=doc.id) if r.role == "enhanced"]
    assert len(enhanced) == 1 and [s["step"] for s in enhanced[0].steps] == ["binarise", "flip"]
    assert step["paper_steps"]["enhanced"] == 1
