"""`compute.tune.set-excludes-flagged-lines` (#5446), tested to the spec through the public routes.

The distillation golden path, as an operator agent drives it over MCP: the teacher reads Kraken's lines,
a checker (Fable, or a person) checks the readings (`POST /api/check/runs`, `POST /api/check/verdicts`),
the operator looks at what the training set would hold (`GET /api/training/set`), and a training job
sends that set. A shifted or `null` line that reaches the set teaches the student the wrong text (the
Mosquera teacher set of 2026-10-04 carried such lines and both trainings on it were cancelled).

The checker model is a stub at the model boundary (`llm.vision`); Hugging Face is `FakeHub`. Nothing here
calls a real model or the Hub.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import fichero_server.llm as llm
from fichero_server.execution import jobs
from fichero_server.models import DocType, Document, Segment
from tests.unit.training.test_kraken_training_set import PAGE, TEACHER, _page

CHECKER = "anthropic/claude-fable"
SIZE = (274, 396)


@pytest.fixture
def checker(monkeypatch):
    """The checker answers with the scripted verdicts in turn, then confirms."""
    script: list[dict] = []

    async def vision(images, prompt, config, **kw):
        verdict = script.pop(0) if script else {"verdict": "confirm", "why": "it reads so"}
        return json.dumps(verdict)

    monkeypatch.setattr(llm, "vision", vision)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)  # the test runs the job itself
    return script


@pytest.fixture
def folder(db):
    made = Document(name="SM_NPQ_C01", doc_type=DocType.folder)
    db.save(made)
    return made


def _teacher_page(db, tmp_path, folder, name="SM_NPQ_C01_001"):
    doc = _page(db, tmp_path, name, folder, size=SIZE)
    doc.metadata = {**(doc.metadata or {}), "width": SIZE[0], "height": SIZE[1]}
    db.save(doc)
    return doc


def _check(client, db, folder):
    r = client.post("/api/check/runs", json={"provider": "openrouter", "model": CHECKER, "layer": "readings",
                                             "scope_ids": [folder.id]})
    assert r.status_code == 200, r.text
    subject = db.execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [r.json()["job_id"]])[0]
    from fichero_server.checking import job as check_job

    check_job.register_job_kinds()
    jobs.KINDS["check"].run(db, subject)
    return r.json()["job_id"]


def _preview(client, folder, **extra):
    r = client.get("/api/training/set", params={"teacher": TEACHER, "scope_ids": [folder.id], **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _segment_of(client, db, doc, reading_id):
    for s in db.query(Segment, document_id=doc.id):
        if any(r["id"] == reading_id for r in client.get(f"/api/segments/{s.id}/readings").json()["items"]):
            return s.id
    raise AssertionError(f"no line carries reading {reading_id}")


def test_a_set_built_before_the_check_says_so(client, db, tmp_path, folder):
    """compute.tune.set-excludes-flagged-lines: "A set built before the check ran says so."
    WHY: a student trained on unchecked teacher lines must not be mistaken for one trained on checked
    lines; the operator reads this before spending a training run."""
    _teacher_page(db, tmp_path, folder)
    made = _preview(client, folder)
    assert made["check_ran"] is False and made["lines_with_a_verdict"] == 0
    assert made["lines"] > 0 and made["pages"] == 1
    assert set(made["flags_checked"]) == {"empty", "null", "rejected"}


def test_a_line_the_checker_rejected_is_left_out_and_counted(client, db, tmp_path, folder, checker):
    """compute.tune.set-excludes-flagged-lines: "a training set leaves out every line ... a person
    rejected, and records on the set ... how many it left out and why, by flag."
    WHY: Fable's reject of a shifted line is worthless if the line still teaches the student."""
    doc = _teacher_page(db, tmp_path, folder)
    before = _preview(client, folder)
    checker.append({"verdict": "reject", "why": "this is the line above's text"})
    run_id = _check(client, db, folder)
    rejects = [v for v in client.get("/api/check/verdicts", params={"run_id": run_id}).json()["items"]
               if v["verdict"] == "reject"]
    assert len(rejects) == 1

    after = _preview(client, folder)
    assert after["check_ran"] is True and after["lines_with_a_verdict"] >= before["lines"]
    assert after["left_out"]["rejected"] == 1 and after["lines"] == before["lines"] - 1
    assert after["lines_left_out"] == before["lines_left_out"] + 1
    (line,) = [x for x in after["left_out_lines"] if x["flag"] == "rejected"]
    assert line == {"document_id": doc.id, "segment_id": _segment_of(client, db, doc, rejects[0]["target_id"]),
                    "flag": "rejected"}


def test_a_persons_later_verdict_brings_the_line_back(client, db, tmp_path, folder, checker):
    """compute.tune.set-excludes-flagged-lines: the line's NEWEST verdict decides.
    WHY: a person who looks at a line Fable rejected and confirms it must get it back into the set;
    an old reject that outlives the person's answer would silently shrink every later set."""
    _teacher_page(db, tmp_path, folder)
    checker.append({"verdict": "reject", "why": "unsure"})
    run_id = _check(client, db, folder)
    (reject,) = [v for v in client.get("/api/check/verdicts", params={"run_id": run_id}).json()["items"]
                 if v["verdict"] == "reject"]
    assert _preview(client, folder)["left_out"]["rejected"] == 1

    r = client.post("/api/check/verdicts", json={"layer": "readings", "target_id": reject["target_id"],
                                                 "verdict": "confirm", "reasons": "it reads so on the page"})
    assert r.status_code == 200, r.text
    assert _preview(client, folder)["left_out"]["rejected"] == 0


def test_a_null_reading_is_left_out(client, db, tmp_path, folder, monkeypatch):
    """compute.tune.set-excludes-flagged-lines: "a null or empty reading" is flagged and left out.
    WHY: a model's null kept as the word `null` (#5447) would teach the student to write `null`."""
    from tests.unit.training import test_kraken_training_set as base

    doc = _teacher_page(db, tmp_path, folder)
    plain = _preview(client, folder)
    nulled = tmp_path / "nulled.page.xml"
    nulled.write_text(PAGE.read_text(encoding="utf-8").replace(
        "<Unicode>y salvedades alli expressadas; Y fue acetada;</Unicode>", "<Unicode>null</Unicode>"),
        encoding="utf-8")
    other = Document(name="SM_NPQ_C02", doc_type=DocType.folder)
    db.save(other)
    monkeypatch.setattr(base, "PAGE", nulled)  # the same page, its teacher answered null for one line
    _page(db, tmp_path, "SM_NPQ_C02_001", other, size=SIZE)

    flagged = _preview(client, other)
    assert flagged["left_out"]["null"] == 1 and flagged["lines"] == plain["lines"] - 1
    assert doc.id not in {x["document_id"] for x in flagged["left_out_lines"]}


def test_the_job_sends_exactly_what_the_preview_counts(client, db, tmp_path, folder, checker, monkeypatch):
    """compute.tune.set-excludes-flagged-lines: the set leaves the line out and "records on the set and on
    the job's card how many it left out and why".
    WHY: the preview is how the operator decides to spend a run; if the job built its set another way the
    count shown would not be the set trained on. And the PAGE file sent to ketos must not hold the line."""
    from fichero_server.formats.harness import xml_id
    from fichero_server.training import job as training_job
    from fichero_server.training.job import TrainKrakenRequest
    from tests.unit.training.test_training_job import FakeHub

    _teacher_page(db, tmp_path, folder)
    checker.append({"verdict": "reject", "why": "shifted"})
    _check(client, db, folder)
    preview = _preview(client, folder)
    (line,) = [x for x in preview["left_out_lines"] if x["flag"] == "rejected"]

    work = tmp_path / "work"
    monkeypatch.setattr(training_job, "_work_dir", lambda job_id: work / job_id)
    hub = FakeHub(stages=("failed",), message="stopped for the test")
    started = training_job.start(db, TrainKrakenRequest(scope_ids=[folder.id], teacher=TEACHER, pages_may_leave=True),
                                 started_by="owner", target_factory=lambda: hub)
    subject = db.execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [started["job_id"]])[0]
    with pytest.raises(Exception, match="stopped for the test"):
        training_job.run(db, subject, target=hub, sleep=lambda s: None)

    sent = client.get(f"/api/training/jobs/{started['job_id']}").json()["training_set"]
    for key in ("lines", "lines_left_out", "left_out", "left_out_lines", "check_ran"):
        assert sent[key] == preview[key], key
    (xml,) = list((work / started["job_id"] / "data").glob("*.xml"))
    written = xml.read_text(encoding="utf-8")
    assert f'id="{xml_id(line["segment_id"])}"' not in written
    from fichero_server.training.kraken_set import read_lines

    assert read_lines(written) == preview["lines"]
    manifest = json.loads((Path(xml).parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["left_out"]["rejected"] == 1
