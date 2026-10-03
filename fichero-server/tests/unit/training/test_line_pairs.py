"""Line pictures and the teacher's readings, as a vision model's training pairs (#5398, `compute.tune.lora`)."""
from __future__ import annotations

import json

import pytest
from PIL import Image

from fichero_server.llm import line_reader
from fichero_server.models import DocType, Document
from fichero_server.training.kraken_set import export_training_set
from fichero_server.training.line_pairs import PAIRS, lines_of, write_line_pairs
from tests.unit.training.test_kraken_training_set import TEACHER, _page

PAGE_SIZE = (2743, 3965)  # the fixture's own page size: its line outlines are in these pixels


@pytest.fixture
def training_set(db, tmp_path):
    folder = Document(name="SM_NPQ_C09", doc_type=DocType.folder)
    db.save(folder)
    _page(db, tmp_path, "SM_NPQ_C09_001", folder, size=PAGE_SIZE)
    out = tmp_path / "set"
    export_training_set(db, scope_ids=[folder.id], teacher=TEACHER, held_out_ids=[], out_dir=out)
    return out


def test_every_read_line_becomes_one_pair_in_the_teachers_own_words(training_set):
    """WHY: the student must learn the teacher's task exactly as the line reader asks it, one
    picture, the same instruction, and the answer in the teacher's form, so it can stand in the
    teacher's place in the same workflow."""
    count = write_line_pairs(training_set, language="Spanish")
    rows = [json.loads(line) for line in (training_set / PAIRS).read_text(encoding="utf-8").splitlines()]
    xml = next(training_set.glob("*.xml")).read_text(encoding="utf-8")

    assert count == len(rows) == len(lines_of(xml)) > 0
    assert {r["prompt"] for r in rows} == {line_reader.prompt_for(1, "Spanish")}
    assert json.loads(rows[0]["answer"]) == [lines_of(xml)[0][1]]
    assert json.loads((training_set / "manifest.json").read_text())["line_pairs"] == count


def test_the_picture_is_the_cut_the_teacher_read(training_set):
    """WHY (`compute.tune.input-is-a-training-set`): a second way of cutting lines would teach the
    student pictures it is never shown; the pair's picture must be `crop_line`'s cut, pixel for pixel."""
    write_line_pairs(training_set)
    row = json.loads((training_set / PAIRS).read_text(encoding="utf-8").splitlines()[0])
    page = Image.open(next(training_set.glob("*.jpg")))
    polygon, _text = lines_of(next(training_set.glob("*.xml")).read_text(encoding="utf-8"))[0]
    assert Image.open(training_set / row["image"]).size == line_reader.crop_line(page, polygon).size


def test_the_line_reader_still_asks_the_same_question():
    """WHY: the prompt was moved into `prompt_for` so the reader and the training pairs share it; the
    reader's batch question must be unchanged by that move."""
    assert line_reader.prompt_for(3, None) == line_reader.PROMPT.format(n=3, language="")
    assert line_reader.prompt_for(1, "es") == line_reader.PROMPT.format(n=1, language=" (in es)")
