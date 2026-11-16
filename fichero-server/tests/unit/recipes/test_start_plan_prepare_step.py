"""The Start plan's Prepare Images step runs the steps the paper answers name: "ruled" runs ruled-lines and "show-through" runs
bleed-through, each recorded on an `enhanced` rendition (`image.enhance.onboarding-step`, `prep.setup.step-runs-from-the-start-plan`,
#5580, #6192). The original is never written."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

from fichero_server.models import DocType, Document, FileType, Rendition
from fichero_server.recipes.start import plan_start
from tests.unit.media.test_enhance_stains_and_ruling import _ruled_page
from tests.unit.recipes.test_start_plan import LINES, _recipe

PREP = {"id": "prep", "job": "prepare-the-image", "model": {"builtin": "image-preparer"}}


def _doc(db, tmp_path, name="ruled.png"):
    path = tmp_path / name
    _ruled_page()[0].save(path)
    doc = Document(name=name, doc_type=DocType.page, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    return doc, path


def test_the_plan_holds_the_prepare_step_before_the_lines_with_the_paper_answers():
    plan = plan_start(_recipe(PREP, LINES), stays_local=True, job_answers={"the_paper": ["ruled", "show-through"]})
    jobs = [r["job"] for r in plan["runs"]]
    assert jobs.index("prepare-the-image") < jobs.index(LINES["job"])
    (run,) = [r for r in plan["runs"] if r["job"] == "prepare-the-image"]
    assert run["paper"] == ["ruled", "show-through"] and "not taken out" not in run["how"]


def test_a_ruled_answer_runs_ruled_lines_and_records_it_on_an_enhanced_rendition_and_leaves_the_original(db, tmp_path):
    from fichero_server.recipes.runner import _run_prepare

    doc, path = _doc(db, tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    step: dict = {}
    assert _run_prepare(db, [doc.id], "run-1", step, paper=["ruled"], operations=[]) == (None, "done", None)
    assert step["paper_steps"]["enhanced"] == 1 and step["paper_steps"]["steps"] == ["ruled-lines"]
    (row,) = [r for r in db.query(Rendition, document_id=doc.id) if r.role == "enhanced"]
    assert [s["step"] for s in row.steps] == ["ruled-lines"] and row.producer_run_id == "run-1"
    stored = Path(db.path).parent / row.path
    assert np.asarray(Image.open(stored).convert("RGB"))[40:42, 10:90].mean() > np.asarray(Image.open(path).convert("RGB"))[40:42, 10:90].mean()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_both_answers_run_in_order_in_one_rendition_and_a_second_run_adds_nothing(db, tmp_path):
    from fichero_server.recipes.runner import _run_prepare

    doc, _path = _doc(db, tmp_path)
    _run_prepare(db, [doc.id], "run-1", {}, paper=["show-through", "ruled"], operations=[])
    again: dict = {}
    _run_prepare(db, [doc.id], "run-2", again, paper=["show-through", "ruled"], operations=[])
    (row,) = [r for r in db.query(Rendition, document_id=doc.id) if r.role == "enhanced"]
    assert [s["step"] for s in row.steps] == ["ruled-lines", "bleed-through"]
    assert again["paper_steps"]["kept"] == 1 and again["paper_steps"]["enhanced"] == 0


def test_without_those_answers_no_enhanced_rendition_is_made(db, tmp_path):
    from fichero_server.recipes.runner import _run_prepare

    doc, _path = _doc(db, tmp_path)
    step: dict = {}
    _run_prepare(db, [doc.id], "run-1", step, paper=["faded"], operations=[])
    assert "paper_steps" not in step and not [r for r in db.query(Rendition, document_id=doc.id) if r.role == "enhanced"]
