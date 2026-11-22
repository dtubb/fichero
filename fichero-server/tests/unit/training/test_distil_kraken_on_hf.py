# ruff: noqa: F811  (a fixture imported from another test file is used by name)
"""Kraken on Hugging Face, end to end, against a fake Hub (`distillation.md` Step 2.1, #5398, #5337).

The real half (a named machine, a real token, a real cap) is a run recorded in the review; nothing here submits a Job.
"""
from __future__ import annotations

import json

import pytest
import yaml

from fichero_server.training import job as training_job
from tests.unit.training.test_training_job import (  # noqa: F401  (fixtures)
    FakeHub, _request, _start, _subject, isolated, notebook,
)

pytestmark = pytest.mark.usefixtures("project_says_yes")


def _set_cap(test_package, cap):
    path = test_package / "recipe" / "setup.yaml"
    answers = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    answers["hf_spend_cap_usd"] = cap
    path.write_text(yaml.safe_dump(answers), encoding="utf-8")


def _queued(db):
    return db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [training_job.KIND])[0]


def test_a_cap_of_zero_refuses_a_training_start_in_words_before_anything_is_sent(db, notebook, test_package):
    """WHY: a $0 cap only held the offer; a direct start paid anyway."""
    _set_cap(test_package, 0)
    hub = FakeHub()
    with pytest.raises(training_job.OverTheCap, match=r"cap is \$0"):
        _start(db, notebook, hub)
    assert _queued(db) == 0 and hub.sent == [] and hub.submitted == []


def test_a_start_whose_price_times_limit_passes_the_cap_is_refused_with_the_sum(db, notebook, test_package):
    """WHY: the most a Job can cost is its hourly price times its time limit (0.4 x 4h = $1.60)."""
    _set_cap(test_package, 1.0)
    with pytest.raises(training_job.OverTheCap, match=r"\$1\.60.*\$1\.00"):
        _start(db, notebook, FakeHub())
    assert _queued(db) == 0


def test_a_start_under_the_cap_is_queued(db, notebook, test_package):
    _set_cap(test_package, 5.0)
    assert _start(db, notebook, FakeHub())["job_id"]


def test_spend_already_this_month_counts_against_the_cap(db, notebook, test_package):
    """WHY: a cap is a monthly ceiling; the second start must see the first (1.60 + 1.60 > 3)."""
    _set_cap(test_package, 3.0)
    _start(db, notebook, FakeHub())
    job_id = db.execute_fetchone("SELECT id FROM jobs WHERE kind = ?", [training_job.KIND])[0]
    _, detail = training_job._row(db, job_id)
    detail["far_id"] = "hf-job-1"  # the first one was sent
    db.execute("UPDATE jobs SET detail = ? WHERE id = ?", [json.dumps(detail), job_id])
    with pytest.raises(training_job.OverTheCap, match="this month"):
        _start(db, notebook, FakeHub())


# --- the held-out score at landing ----------------------------------------------------------------------------

def _trained_and_landed(db, notebook, tmp_path, monkeypatch, *, person_checked=True, **over):
    """A training run to its landing against the fake Hub; returns (job id, reader id)."""
    from fichero_server.execution import jobs
    from tests.unit.training.test_evaluation_job import _checked

    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    if person_checked:
        _checked(db, tmp_path, notebook.test_page, by_a_person=True)
    hub = FakeHub()
    started = _start(db, notebook, hub, **over)
    reader = training_job.run(db, _subject(db, started["job_id"]), target=hub, sleep=lambda s: None)
    return started["job_id"], reader


def test_landing_starts_the_evaluation_job_on_the_held_out_pages(db, notebook, tmp_path, monkeypatch):
    """WHY (`distill.eval.job`): the held-out pages stayed home and nothing scored them unless a person started the
    evaluation by hand; a reader must be measured when it lands."""
    job_id, reader = _trained_and_landed(db, notebook, tmp_path, monkeypatch)

    score = training_job.status(db, job_id)["held_out_score"]
    assert score["state"] == "scoring"
    row = db.execute_fetchone("SELECT kind, detail FROM jobs WHERE id = ?", [score["evaluation_job_id"]])
    assert row[0] == "evaluate-models"
    request = json.loads(row[1])["request"]
    assert [c["model"] for c in request["candidates"]] == [reader] and request["held_out_ids"] == [notebook.test_page.id]


def test_the_score_the_evaluation_measures_is_on_the_readers_card_with_its_cer_and_lines(
        db, notebook, tmp_path, monkeypatch):
    """WHY: a person reads the held-out CER on the card of the reader, not in a job's log."""
    from fichero_server.execution import jobs
    from fichero_server.llm import kraken_runtime
    from fichero_server.training import evaluation

    job_id, reader = _trained_and_landed(db, notebook, tmp_path, monkeypatch)
    monkeypatch.setattr(kraken_runtime, "read_given_lines", lambda image, model, lines, **kw: [ln["text"] for ln in lines])
    eval_id = training_job.status(db, job_id)["held_out_score"]["evaluation_job_id"]
    subject = db.execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [eval_id])[0]
    evaluation.register_job_kinds()
    jobs.KINDS[evaluation.KIND].run(db, subject)

    (entry,) = evaluation.model_evaluations(reader, "kraken")
    assert entry["job_id"] == eval_id and entry["scores"]["diplomatic"]["cer"] == 0.0
    assert entry["lines"] > 0 and entry["pages_read"] == 1


def test_a_reader_with_nothing_to_score_says_why_and_still_lands(db, notebook, tmp_path, monkeypatch):
    """WHY: no person's reading on the held-out page means no fair score; the card says so (`not measured`), the
    trained reader still lands, and no evaluation is queued to fail later."""
    job_id, reader = _trained_and_landed(db, notebook, tmp_path, monkeypatch, person_checked=False)
    status = training_job.status(db, job_id)
    assert status["state"] != "failed" and status["reader_id"] == reader
    assert status["held_out_score"]["state"] == "not measured" and "reading" in status["held_out_score"]["why"]
    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = 'evaluate-models'")[0] == 0


def test_no_held_out_pages_is_not_measured_in_words(db, notebook, tmp_path, monkeypatch):
    job_id, _ = _trained_and_landed(db, notebook, tmp_path, monkeypatch, held_out_ids=[])
    assert training_job.status(db, job_id)["held_out_score"] == {
        "state": "not measured", "why": "no held-out corrected pages"}


# --- the card names its teacher -------------------------------------------------------------------------------

def test_the_card_names_the_teacher_in_words(db, notebook, tmp_path, monkeypatch):
    """WHY (`distill.train.card-names-teacher`): `teacher` is a raw id (or `person`); a person reading the card needs
    who taught the reader, in words, on the card."""
    from fichero_server.llm import kraken_runtime as kr
    from tests.unit.training.test_kraken_training_set import TEACHER

    _, reader = _trained_and_landed(db, notebook, tmp_path, monkeypatch)
    assert kr.trained_reader_card(reader)["taught_by"] == TEACHER


# --- the gate before a reader can be offered ------------------------------------------------------------------

@pytest.mark.parametrize(("trained", "current", "verdict", "words"), [
    (0.05, 0.08, "better", "better by 3.0 points on 40 pages"),
    (0.079, 0.08, "too close", "too close to call"),
    (0.09, 0.08, "worse", "worse: kept, not offered"),
    (None, 0.08, "not measured", "not measured: no held-out corrected pages"),
])
def test_the_gate_gives_one_of_four_verdicts_in_the_specs_words(trained, current, verdict, words):
    from fichero_server.training import gate

    got = gate.verdict(trained, current, band=0.005, pages=40)
    assert got["verdict"] == verdict and got["words"] == words


def test_a_worse_reader_is_inside_the_band_only_when_it_is_close(db):
    """WHY: 'too close to call' is both ways inside the band; a reader worse by more is 'worse', not 'close'."""
    from fichero_server.training import gate

    assert gate.verdict(0.083, 0.08, band=0.005, pages=20)["verdict"] == "too close"
    assert gate.verdict(0.0851, 0.08, band=0.005, pages=20)["verdict"] == "worse"


def test_the_evaluation_writes_the_verdict_on_the_trained_readers_card_entry(db, notebook, tmp_path, monkeypatch):
    """WHY: a landed reader is not offered as a replacement until a card says it is better; with no verdict it is
    `not measured`. The trained reader reads perfectly, the base drops a character a line: better."""
    from fichero_server.execution import jobs
    from fichero_server.llm import kraken_runtime
    from fichero_server.training import evaluation
    from tests.unit.training.test_evaluation_job import BASE, Readers, _base_installed

    base_path = _base_installed(tmp_path)  # on this Mac before landing: the evaluation is planned at landing
    job_id, reader = _trained_and_landed(db, notebook, tmp_path, monkeypatch)
    monkeypatch.setattr(evaluation, "NOISE_MIN_PAGES", 1)  # one held-out page here; the floor is 15 for real
    fake = Readers(trained_path=kraken_runtime.recognition_model_path(reader))
    monkeypatch.setattr(kraken_runtime, "read_given_lines", fake)
    eval_id = training_job.status(db, job_id)["held_out_score"]["evaluation_job_id"]
    subject = db.execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [eval_id])[0]
    evaluation.register_job_kinds()
    jobs.KINDS[evaluation.KIND].run(db, subject)

    assert base_path in fake.read, "the base reader was measured on the same page"
    (entry,) = evaluation.model_evaluations(reader, "kraken")
    assert entry["verdict"]["verdict"] == "better" and "points on 1 page" in entry["verdict"]["words"], BASE
    (base_entry,) = evaluation.model_evaluations(BASE, "kraken")
    assert base_entry["verdict"] is None


def test_too_few_held_out_pages_are_not_measured_in_words(db, notebook, tmp_path, monkeypatch):
    from fichero_server.execution import jobs
    from fichero_server.llm import kraken_runtime
    from fichero_server.training import evaluation
    from tests.unit.training.test_evaluation_job import Readers, _base_installed

    _base_installed(tmp_path)
    job_id, reader = _trained_and_landed(db, notebook, tmp_path, monkeypatch)
    monkeypatch.setattr(kraken_runtime, "read_given_lines", Readers(trained_path=kraken_runtime.recognition_model_path(reader)))
    eval_id = training_job.status(db, job_id)["held_out_score"]["evaluation_job_id"]
    evaluation.register_job_kinds()
    jobs.KINDS[evaluation.KIND].run(db, db.execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [eval_id])[0])

    (entry,) = evaluation.model_evaluations(reader, "kraken")
    assert entry["verdict"]["verdict"] == "not measured" and "1 held-out page" in entry["verdict"]["words"]


def test_the_catalogue_says_a_readers_verdict_or_that_it_has_none(db, notebook, tmp_path, monkeypatch):
    """WHY: the verdict is the gate a person sees before choosing the reader; none yet is said, never left blank."""
    from fichero_server.llm.local_model_catalog import kraken_catalog_entries

    _, reader = _trained_and_landed(db, notebook, tmp_path, monkeypatch)
    (entry,) = [e for e in kraken_catalog_entries() if e.model_id == reader]
    assert "Not measured: no verdict yet, so it is not offered as a replacement." in entry.note
