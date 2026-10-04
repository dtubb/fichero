"""A palaeographer's reasons for each checked line, kept in the episode ledger (#4642).

The teacher is a stand-in that records its calls (the spec's test matrix); the checked pass, the line
pictures, the ledger and the reading back by line id are real.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from fichero_server.models import DocType, Document
from fichero_server.models.segments import SegmentPass
from fichero_server.page_export import export_page
from fichero_server.training import reasons
from fichero_server.training.line_pairs import lines_with_ids
from tests.unit.training.test_kraken_training_set import _page

CHECKED = "fable-checked"
DRAFT = "google/gemini-3-flash-preview"
SIZE = (274, 396)  # the fixture page at a tenth of its size


class Teacher:
    """Answers each line with reasons; `think` adds a thinking block; `garble` spoils the first answer."""

    def __init__(self, mode=reasons.READ, think=False, garble=False):
        self.mode, self.think, self.garble = mode, think, garble
        self.prompts: list[str] = []

    async def __call__(self, images, prompt):
        self.prompts.append(prompt)
        if self.garble:
            self.garble = False
            return "I cannot say."
        if self.mode == reasons.READ:
            items = [{"letterforms": "long s", "abbreviations": [{"as_written": "q̃", "expanded": "que"}],
                      "uncertain": [], "text": f"line {len(self.prompts)}.{i}"} for i in range(len(images))]
        else:
            items = [{"verdict": "corrected", "text": "fixed", "why": "the ascender is an l"} for _ in images]
        answer = json.dumps(items, ensure_ascii=False)
        return f"<think>The second letter has a loop.</think>{answer}" if self.think else answer


@pytest.fixture
def project(db, tmp_path):
    folder = Document(name="SM_NPQ_C01", doc_type=DocType.folder)
    db.save(folder)
    pages = []
    for name in ("SM_NPQ_C01_001", "SM_NPQ_C01_002"):
        page = _page(db, tmp_path, name, folder, read_by=CHECKED, size=SIZE)
        page.metadata = {**(page.metadata or {}), "width": SIZE[0], "height": SIZE[1]}  # as an import records it
        db.save(page)
        pages.append(page)
    return folder, *pages


def _library(db) -> str:
    return str(Path(db.path).parent)


def _ledger(db) -> list[dict]:
    return [json.loads(line) for path in sorted((Path(_library(db)) / "episodes").glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()]


def test_every_checked_line_gets_its_reasons_in_the_ledger_found_again_by_its_line_id(db, project):
    """WHY (`distill.reasoning.traces-in-the-ledger`): the set builder must find each line's reasons
    beside that line's CHECKED answer. One episode a call, the thinking kept, the held-out page never
    asked about (it is the test), and the ids the same ones the checked pass's PAGE export gives."""
    folder, kept, test = project
    lines, photos, missing = reasons.checked_lines(db, scope_ids=[folder.id], checked=CHECKED,
                                                   held_out_ids=[test.id])
    assert not missing and set(photos) == {kept.id} and {line.document_id for line in lines} == {kept.id}
    teacher = Teacher(think=True)
    done = asyncio.run(reasons.collect(lines, photos, mode=reasons.READ, ask=teacher,
                                       model={"provider": "omlx", "model": "Qwen3-VL-8B-Thinking"},
                                       library_path=_library(db), language="Spanish",
                                       prompt_file="recipes/spanish/palaeographer.txt"))

    assert done.calls == done.reasoned == done.with_thinking == len(lines) > 0
    episodes = _ledger(db)
    assert len(episodes) == len(lines)
    first = episodes[0]
    assert first["model"]["use_case"] == "palaeography-reasons"
    assert first["model"]["prompt_file"] == "recipes/spanish/palaeographer.txt"
    assert first["exchange"]["thinking"] == "The second letter has a loop." and "(in Spanish)" in first["exchange"]["prompt"]

    pass_id = next(p for p in db.query(SegmentPass, document_id=kept.id)).id
    ids = [i for i, _p, _t in lines_with_ids(export_page(db, kept.id, "pagexml", pass_id=pass_id).data.decode())]
    found = reasons.traces_by_line(_library(db))
    assert set(found) == set(ids)
    one = found[ids[0]]
    assert one["thinking"] and one["abbreviations"][0]["expanded"] == "que" and one["episode_id"].startswith("ep_")


def test_the_reviewer_sees_each_lines_draft_and_says_why(db, project, tmp_path):
    """WHY (the palaeographer reviewer): a review is only about a reading if the reviewer is shown that
    reading. Drafts come from another pass, matched to each checked line by its outline."""
    folder, kept, _test = project
    from fichero_server.actions.registry import registry
    from tests.unit.training.test_kraken_training_set import BOOT, PAGE

    copy = tmp_path / "draft.page.xml"
    copy.write_bytes(PAGE.read_bytes() + b"\n")  # the same lines, another file: not refused as already imported
    registry.invoke(db, "format.import", {"document_id": kept.id, "path": str(copy), "name": "draft"}, BOOT)
    draft = next(p for p in db.query(SegmentPass, document_id=kept.id) if p.model != CHECKED)
    draft.model = DRAFT
    db.save(draft)

    lines, photos, _ = reasons.checked_lines(db, scope_ids=[kept.id], checked=CHECKED, draft=DRAFT)
    assert lines and all(line.draft == line.checked for line in lines)  # the same file: every line matches
    teacher = Teacher(mode=reasons.REVIEW)
    asyncio.run(reasons.collect(lines[:3], photos, mode=reasons.REVIEW, ask=teacher, model={"model": "fable"},
                                library_path=_library(db)))
    assert json.dumps(lines[0].draft, ensure_ascii=False) in teacher.prompts[0]
    found = reasons.traces_by_line(_library(db), reasons.REVIEW)
    assert found[lines[0].line_id]["why"] == "the ascender is an l" and found[lines[0].line_id]["draft"] == lines[0].draft


def test_a_batch_that_cannot_be_matched_is_asked_again_line_by_line(db, project):
    """WHY: a reason placed on the wrong line teaches the student a wrong reason; the line reader's own
    rule holds here too."""
    folder, kept, _test = project
    lines, photos, _ = reasons.checked_lines(db, scope_ids=[kept.id], checked=CHECKED)
    teacher = Teacher(garble=True)
    done = asyncio.run(reasons.collect(lines[:4], photos, mode=reasons.READ, ask=teacher, model={},
                                       library_path=_library(db), per_call=4))
    assert len(teacher.prompts) == 5 and done.reasoned == 4 and done.unparsed == 0
    assert all(len(e["lines"]) == 1 for e in _ledger(db))


@pytest.mark.parametrize("raw,answer,thinking", [
    ("<think>loop on the d</think>[1]", "[1]", "loop on the d"),
    ("the d is looped</think>\n[1]", "[1]", "the d is looped"),  # Qwen3's template opens <think> itself
    ("[1]", "[1]", None),
])
def test_thinking_is_split_from_the_answer(raw, answer, thinking):
    """WHY: a thinking block left in the answer fails the JSON parse and the line is lost."""
    assert reasons.split_thinking(raw) == (answer, thinking)
