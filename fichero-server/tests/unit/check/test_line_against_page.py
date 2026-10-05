"""`source.lines.reading-checked-against-the-page` (#5446), tested to the spec through the public routes.

The teacher (Gemini) read the lines Kraken found; on the Mosquera set a quarter of a trial's lines held the
text of the line above. The check reads each line again with a Kraken reader (a rough read) and scores the
teacher's reading against that line's rough read and its neighbours'. Flagged lines must then leave the
training set (`compute.tune.set-excludes-flagged-lines`) with no other step.

Everything goes through `POST /api/check/runs` (check `line-against-page`), the job as the scheduler runs it
(`jobs.KINDS["check-lines"].run`), `GET /api/check/runs/{id}`, `/api/check/verdicts` and `GET /api/training/set`.
Kraken is faked at its seam (`kraken_runtime.read_given_lines`): no torch, no model, no training.
"""
from __future__ import annotations

import pytest

from fichero_server.checking import line_check
from fichero_server.execution import jobs
from fichero_server.formats.harness import xml_id
from fichero_server.llm import kraken_runtime
from fichero_server.models import DocType, Document
from tests.unit.training.test_kraken_training_set import TEACHER, _page

READER = "kraken-mccatmus"
SIZE = (274, 396)


class RoughReader:
    """Kraken's reader, faked at the seam: each line reads as the teacher read it (a perfect rough read)
    unless the test says otherwise. Records the lines it was given."""

    def __init__(self):
        self.lines: list[dict] = []
        self.plan = lambda lines: {}

    def __call__(self, image_path, model_path, lines, **kw):
        assert model_path == "/models/mccatmus.mlmodel"
        self.lines = list(lines)
        override = self.plan(self.lines)
        return [override.get(i, line["text"]) for i, line in enumerate(self.lines)]


@pytest.fixture
def reader(monkeypatch):
    fake = RoughReader()
    monkeypatch.setattr(kraken_runtime, "read_given_lines", fake)
    monkeypatch.setattr(kraken_runtime, "resolve_recognition_model", lambda ref: ("/models/mccatmus.mlmodel", ref))
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)  # the test runs the job itself
    return fake


@pytest.fixture
def folder(db, tmp_path):
    made = Document(name="SM_NPQ_C01", doc_type=DocType.folder)
    db.save(made)
    doc = _page(db, tmp_path, "SM_NPQ_C01_001", made, size=SIZE)
    doc.metadata = {**(doc.metadata or {}), "width": SIZE[0], "height": SIZE[1]}
    db.save(doc)
    return made


def _column(lines, i, j):
    return line_check._same_column(lines[i]["polygon"], lines[j]["polygon"])


def _shift_at(lines) -> int:
    """A body line with long, distinct text and a same-column line below it."""
    return next(i for i in range(2, len(lines) - 3) if len(lines[i]["text"]) >= 20
                and len(lines[i + 1]["text"]) >= 20 and _column(lines, i, i + 1))


def _poor_at(lines, after: int) -> int:
    """A line well clear of `after` whose neighbours' texts do not explain it (none agrees by 0.40)."""
    for i in range(after + 5, len(lines)):
        near = [j for j in range(i - 2, min(len(lines), i + 3)) if j != i and _column(lines, i, j)]
        if len(lines[i]["text"]) >= 15 and all(
                line_check.agreement(lines[i]["text"], lines[j]["text"]) < 0.4 for j in near):
            return i
    raise AssertionError("no suitable line in the fixture")


def _run(client, db, folder, **extra):
    r = client.post("/api/check/runs", json={"check": "line-against-page", "provider": "kraken", "model": READER,
                                             "layer": "readings", "scope_ids": [folder.id], "pass_model": TEACHER,
                                             **extra})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    assert kind == "check-lines"
    from fichero_server.checking import job as check_job

    check_job.register_job_kinds()
    jobs.KINDS[kind].run(db, subject)
    status = client.get(f"/api/check/runs/{job_id}")
    assert status.status_code == 200, status.text
    return job_id, status.json()


def _flag_of(status, line_id):
    return [f["flag"] for f in status["flagged"] if xml_id(f["segment_id"]) == line_id]


def test_a_misaligned_line_is_flagged_closer_to_a_neighbour(client, db, folder, reader):
    """source.lines.reading-checked-against-the-page: "a reading that matches a neighbour clearly better than
    its own line ... [is] flagged, with the scores".
    WHY: this is the Mosquera defect: the teacher gave a line the text of the line beside it. Kraken's rough
    read of the line below says what the teacher wrote; its own line's rough read does not."""
    picked = {}

    def plan(lines):
        k = picked.setdefault("k", _shift_at(lines))
        return {k: "", k + 1: lines[k]["text"]}

    reader.plan = plan
    job_id, status = _run(client, db, folder)
    k = picked["k"]
    assert _flag_of(status, reader.lines[k]["id"]) == ["closer to a neighbour"]
    (flag,) = [f for f in status["flagged"] if xml_id(f["segment_id"]) == reader.lines[k]["id"]]
    assert flag["offset"] == 1 and flag["neighbour"] == 1.0 and flag["own"] == 0.0
    assert status["counts"]["closer_to_a_neighbour"] >= 1
    assert status["thresholds"] == {"neighbours": 2, "shift_margin": 0.15, "shift_floor": 0.4, "low": 0.3,
                                    "policy": "accent-blind"}
    verdicts = client.get("/api/check/verdicts", params={"target_id": flag["reading_id"]}).json()["items"]
    (verdict,) = verdicts
    assert verdict["verdict"] == "reject" and verdict["trust"] == "model" and verdict["checker"] == READER
    assert verdict["run_id"] == job_id and verdict["reasons"].startswith("closer to a neighbour")


def test_a_poor_line_is_flagged_below_the_threshold(client, db, folder, reader):
    """source.lines.reading-checked-against-the-page: a reading "below a set score" is flagged.
    WHY: a reading that agrees with nothing on the page (the teacher misread, or read nothing that is
    there) must not teach the student, even when no neighbour explains it."""
    picked = {}

    def plan(lines):
        m = picked.setdefault("m", _poor_at(lines, 0))
        return {m: lines[m]["text"][:3]}

    reader.plan = plan
    _job_id, status = _run(client, db, folder)
    assert _flag_of(status, reader.lines[picked["m"]]["id"]) == ["below the threshold"]
    assert status["counts"]["below_the_threshold"] == 1 and status["counts"]["closer_to_a_neighbour"] == 0


def test_a_good_line_passes_and_gets_no_verdict(client, db, folder, reader):
    """source.lines.reading-checked-against-the-page: only flagged lines are marked.
    WHY: a passing line gets no verdict at all: a confirm from a rough reader would be the line's newest
    verdict and would bring back a line Fable had rejected."""
    _job_id, status = _run(client, db, folder)
    scored = len([ln for ln in reader.lines if ln["text"] and ln["text"].casefold() != "null"])
    assert status["counts"]["passed"] == scored > 0
    assert status["flagged"] == []
    assert client.get("/api/check/verdicts", params={"layer": "readings"}).json()["count"] == 0


def test_flagged_lines_leave_the_training_set_counted(client, db, folder, reader):
    """compute.tune.set-excludes-flagged-lines: "a training set leaves out every line the reading check
    flagged ... and records ... how many it left out".
    WHY: a flag that does not keep the line out of the set changes nothing the student learns."""
    def preview():
        r = client.get("/api/training/set", params={"teacher": TEACHER, "scope_ids": [folder.id]})
        assert r.status_code == 200, r.text
        return r.json()

    before = preview()
    picked = {}

    def plan(lines):
        k = picked.setdefault("k", _shift_at(lines))
        m = picked.setdefault("m", _poor_at(lines, k + 1))
        return {k: "", k + 1: lines[k]["text"], m: ""}

    reader.plan = plan
    _job_id, status = _run(client, db, folder)
    flagged = len(status["flagged"])
    assert flagged >= 2
    after = preview()
    assert after["check_ran"] is True
    assert after["left_out"]["rejected"] == flagged and after["lines"] == before["lines"] - flagged
    assert {f["segment_id"] for f in status["flagged"]} == {
        x["segment_id"] for x in after["left_out_lines"] if x["flag"] == "rejected"}


def test_a_persons_later_confirm_brings_the_line_back_and_a_rerun_leaves_it(client, db, folder, reader):
    """source.lines.reading-checked-against-the-page: a flagged line is kept out "until checked"
    (ruled 2026-10-04, #5444): a person's verdict decides.
    WHY: a person who looks and confirms must get the line back, and the next check must not take it out
    again behind their back."""
    picked = {}

    def plan(lines):
        m = picked.setdefault("m", _poor_at(lines, 0))
        return {m: ""}

    reader.plan = plan
    _job_id, status = _run(client, db, folder)
    (flag,) = status["flagged"]
    r = client.post("/api/check/verdicts", json={"layer": "readings", "target_id": flag["reading_id"],
                                                 "verdict": "confirm", "reasons": "it reads so on the page"})
    assert r.status_code == 200, r.text
    preview = client.get("/api/training/set", params={"teacher": TEACHER, "scope_ids": [folder.id]}).json()
    assert preview["left_out"]["rejected"] == 0

    _job_id, again = _run(client, db, folder)
    assert again["flagged"] == [] and again["counts"]["checked_by_a_person"] == 1


def test_the_check_is_a_job_on_the_local_model_lane(client, db, folder, reader):
    """source.check.run-is-a-job: a check run is one row in Activity.
    WHY: Kraken loads a reader on this Mac; on the remote lane it could run beside another heavy model."""
    job_id, status = _run(client, db, folder)
    assert jobs.KINDS["check-lines"].lane == "local-ml"
    assert status["reason"].startswith(f"{status['counts']['passed']} passed")


def test_the_line_check_refuses_a_layer_or_reader_it_cannot_check(client, db, folder, reader):
    """WHY: a line check of statements, or with a cloud model as the reader, would queue a job that
    can only fail; it is refused when asked."""
    for bad in ({"layer": "claims"}, {"provider": "openrouter"}):
        body = {"check": "line-against-page", "provider": "kraken", "model": READER, "layer": "readings",
                "scope_ids": [folder.id], **bad}
        assert client.post("/api/check/runs", json=body).status_code == 422


def test_the_rule_and_thresholds_are_the_scripts():
    """The rule of the Sergio project's teacher_line_check.py, ported: a neighbour must beat the line's own
    score by 0.15 and score 0.40 itself; else under 0.30 is low.
    WHY: the thresholds were tuned on Mosquera's flagged crops; a drift here changes what trains."""
    box = [(0.0, 0.0), (10.0, 0.0), (10.0, 1.0)]
    lines = [{"text": t, "polygon": box} for t in ("el dicho escribano", "vecino de la ciudad", "y lo firmo")]
    assert [s["flag"] for s in line_check.flag_lines(lines, [t["text"] for t in lines])] == [None, None, None]
    shifted = line_check.flag_lines(lines, ["", "el dicho escribano", "y lo firmo"])
    assert shifted[0]["flag"] == "closer to a neighbour" and shifted[0]["offset"] == 1
    other_column = [dict(lines[0]), {**lines[1], "polygon": [(20.0, 0.0), (30.0, 0.0), (30.0, 1.0)]}]
    assert line_check.flag_lines(other_column, ["", "el dicho escribano"])[0]["flag"] == "below the threshold"
    assert line_check.agreement("Él dicho, escribano", "el dicho escribano") == 1.0


def test_the_rough_read_goes_through_the_kraken_seam(monkeypatch):
    """WHY: every Kraken call passes the one seam (#4959: one lock, memory checked first); a reader called
    around it could load a second model beside the first."""
    lines = [{"id": "l1", "baseline": [(0, 5), (9, 5)], "polygon": [(0, 0), (9, 0), (9, 9)]}]
    called = []

    def seam(op):
        called.append(op)
        return ["read"]

    monkeypatch.setattr(kraken_runtime, "_kraken_call", seam)
    assert kraken_runtime.read_given_lines("/x.png", "/m.mlmodel", lines) == ["read"] and len(called) == 1
    assert kraken_runtime.read_given_lines("/x.png", "/m.mlmodel", [{"id": "l2", "baseline": [], "polygon": []}]) == [""]
    assert len(called) == 1
