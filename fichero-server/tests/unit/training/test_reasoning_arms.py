"""The reasons A/B's training set and its arms (#4642, `distill.reasoning.two-arms`, `.answer-is-checked`).

The palaeographer's traces are written as the ledger gives them back (`training.reasons.traces_by_line`);
the set, the line pictures, the CER rule, the trainer's choice of pairs and the job's refusal are real.
"""
from __future__ import annotations

import json

import pytest

from fichero_server.execution import jobs
from fichero_server.models import DocType, Document
from fichero_server.training import hf_vision_lora_train as trainer
from fichero_server.training import job as training_job
from fichero_server.training.kraken_set import export_training_set
from fichero_server.training.line_pairs import PAIRS, lines_with_ids, write_line_pairs
from tests.unit.training.test_kraken_training_set import TEACHER, _page
from tests.unit.training.test_line_pairs import PAGE_SIZE
from tests.unit.training.test_training_job import FakeHub, _subject


@pytest.fixture
def checked_set(db, tmp_path):
    folder = Document(name="SM_NPQ_C01", doc_type=DocType.folder)
    db.save(folder)
    _page(db, tmp_path, "SM_NPQ_C01_001", folder, size=PAGE_SIZE)
    out = tmp_path / "set"
    export_training_set(db, scope_ids=[folder.id], teacher=TEACHER, held_out_ids=[], out_dir=out)
    xml = next(out.glob("*.xml")).read_text(encoding="utf-8")
    return out, lines_with_ids(xml), folder


def _pairs(out):
    return [json.loads(line) for line in (out / PAIRS).read_text(encoding="utf-8").splitlines()]


def test_every_arm_answers_with_the_checked_text_and_a_wrong_reading_brings_no_reasons(checked_set):
    """WHY (`distill.reasoning.answer-is-checked`): a student that learns reasons for a reading the
    teacher got wrong learns to argue for wrong readings. Line 1's teacher read it right (reasons and
    thinking kept, answer the checked text); line 2's read it wrong (dropped, counted); line 3 has none."""
    out, lines, _ = checked_set
    (id1, _, text1), (id2, _, _text2) = lines[0], lines[1]
    traces = {
        id1: {"text": text1, "letterforms": "long s", "abbreviations": [], "uncertain": [], "thinking": "a loop"},
        id2: {"text": "something else entirely", "letterforms": "x", "thinking": "wrong"},
    }
    write_line_pairs(out, language="Spanish", traces=traces, reviews={})
    pairs = {p["line_id"]: p for p in _pairs(out)}

    one = pairs[id1]["arms"]
    assert set(one) == {"answer", "why", "thinking"}
    assert json.loads(one["why"]["answer"])[0]["text"] == text1 and json.loads(one["why"]["answer"])[0]["letterforms"] == "long s"
    assert one["thinking"]["answer"].startswith("<think>\na loop\n</think>") and one["thinking"]["answer"].endswith(
        json.dumps([text1], ensure_ascii=False))
    assert set(pairs[id2]["arms"]) == {"answer"} and pairs[id1]["in_every_arm"] and not pairs[id2]["in_every_arm"]
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["arms_dropped_outside_cer"]["why"] == 1 and manifest["arms_dropped_outside_cer"]["thinking"] == 1
    assert manifest["arms"]["why"] == 1 and manifest["lines_in_every_arm"] == 1 and manifest["arms"]["answer"] == len(lines)


def test_a_review_pair_is_the_draft_and_the_checked_reading_with_the_reviewers_reason(checked_set):
    """WHY (the palaeographer reviewer): the reviewer student must see the draft it reviews, and learn
    the checked reading and a reason only where the reviewer itself got the line right."""
    out, lines, _ = checked_set
    (id1, _, text1), (id2, _, text2) = lines[0], lines[1]
    reviews = {id1: {"draft": text1 + "x", "text": text1, "why": "no final x: the stroke is the margin"},
               id2: {"draft": text2, "text": "far from it all", "why": "?"}}
    write_line_pairs(out, traces={}, reviews=reviews)
    pairs = {p["line_id"]: p for p in _pairs(out)}
    review = pairs[id1]["arms"]["review"]
    assert json.dumps(text1 + "x", ensure_ascii=False) in review["prompt"]
    assert json.loads(review["answer"]) == [{"verdict": "corrected", "text": text1,
                                             "why": "no final x: the stroke is the margin"}]
    assert "review" not in pairs[id2]["arms"]


def test_the_arms_are_trained_on_the_same_lines():
    """WHY (`distill.reasoning.two-arms`): if the answer-only student saw lines the reasoning student
    did not, the A/B would measure the lines, not the reasons."""
    pairs = [{"image": "a", "prompt": "p", "answer": "A", "in_every_arm": True,
              "arms": {"answer": {"prompt": "p", "answer": "A"}, "why": {"prompt": "q", "answer": "W"},
                       "review": {"prompt": "r", "answer": "R"}}},
             {"image": "b", "prompt": "p", "answer": "B", "in_every_arm": False,
              "arms": {"answer": {"prompt": "p", "answer": "B"}, "review": {"prompt": "r", "answer": "R2"}}},
             {"image": "c", "prompt": "p", "answer": "C"}]  # a set made before reasons
    assert [p["image"] for p in trainer.select(pairs, "answer")] == ["a", "c"]
    assert [(p["image"], p["answer"]) for p in trainer.select(pairs, "why")] == [("a", "W")]
    assert [p["image"] for p in trainer.select(pairs, "answer", all_lines=True)] == ["a", "b", "c"]
    assert [p["answer"] for p in trainer.select(pairs, "review")] == ["R", "R2"]


def test_a_reasoning_arm_without_reasons_is_refused_and_one_with_them_is_sent_with_its_arm(db, checked_set,
                                                                                          tmp_path, monkeypatch):
    """WHY: a `why` student trained on a set with no reasons is an answer-only student under the wrong
    name, and the A/B would compare a model with itself."""
    from pathlib import Path

    from fichero_server.training.job import TrainVisionLoraRequest
    from fichero_server.training.reasons import USE_CASE

    _out, lines, folder = checked_set
    monkeypatch.setattr(training_job, "_work_dir", lambda job_id: tmp_path / "work" / job_id)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    request = TrainVisionLoraRequest(scope_ids=[folder.id], teacher=TEACHER, arm="why", pages_may_leave=True)
    hub = FakeHub()
    started = training_job.start(db, request, started_by="historian", target_factory=lambda: hub)
    with pytest.raises(Exception, match="no line in scope has the why arm"):
        training_job.run(db, _subject(db, started["job_id"]), target=hub, sleep=lambda s: None)
    assert hub.submitted == []

    ledger = Path(db.path).parent / "episodes"
    ledger.mkdir(exist_ok=True)
    (ledger / "2026-10.jsonl").write_text(json.dumps({
        "episode_id": "ep_1", "kind": "model_call", "model": {"use_case": USE_CASE["read"], "model": "thinker"},
        "lines": [{"line_id": lines[0][0], "text": lines[0][2], "letterforms": "a loop"}]}) + "\n")
    hub = FakeHub(stages=("failed",), message="stopped here for the test")  # what was SENT is the point
    again = training_job.start(db, request, started_by="historian", target_factory=lambda: hub)
    with pytest.raises(Exception, match="stopped here for the test"):
        training_job.run(db, _subject(db, again["job_id"]), target=hub, sleep=lambda s: None)
    args = hub.submitted[0]["script_args"]
    assert args[args.index("--arm") + 1] == "why" and "--all-lines" not in args
