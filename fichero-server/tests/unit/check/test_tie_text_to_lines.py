"""`source.job.tie-text-to-lines` (#5444), tested to the spec through the public routes.

A page read whole by a model has good text and no lines; Kraken found the lines and reads each roughly.
The page text is aligned in order to the rough reads and each line gets the stretch it matches: tied
automatically where the stretch agrees with the line's rough read above the threshold, flagged for review
(and kept out of the training set) below it (ruled 2026-10-04).

Everything goes through `POST /api/check/runs` (check `tie-text-to-lines`), the job as the scheduler runs
it (`jobs.KINDS["tie-text-to-lines"].run`), `GET /api/check/runs/{id}`, `/api/check/verdicts`,
`GET /api/segments/{id}/readings` and `GET /api/training/set`. Kraken is faked at its seam
(`kraken_runtime.read_given_lines`): no torch, no model, no training.
"""
from __future__ import annotations

import pytest

from fichero_server.checking import tie_text
from fichero_server.execution import jobs
from fichero_server.formats.harness import xml_id
from fichero_server.llm import kraken_runtime
from fichero_server.models import Artifact, ContentRepresentation, DocType, Document, Segment
from fichero_server.models.checking import CheckVerdict
from fichero_server.models.segments import SegmentPass
from tests.unit.training.test_kraken_training_set import TEACHER, _page

READER = "kraken-mccatmus"
LINES = "kraken-blla"


class RoughReader:
    """Kraken's reader, faked at the seam: each line reads as its own text unless the test says otherwise."""

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


def _texts_in_order(db, doc_id, pass_id):
    from fichero_server.checking.line_check import page_lines
    from fichero_server.page_export import export_page

    return [ln["text"] for ln in page_lines(export_page(db, doc_id, "pagexml", pass_id=pass_id).data.decode("utf-8"))]


@pytest.fixture
def page(db, tmp_path):
    """A page whose lines Kraken found (the imported pass, marked as Kraken's) and whose text the teacher
    read whole: the page reading is the lines' texts, one after another, as one transcription."""
    folder = Document(name="SM_NPQ_C01", doc_type=DocType.folder)
    db.save(folder)
    doc = _page(db, tmp_path, "SM_NPQ_C01_001", folder, read_by=LINES, size=(274, 396))
    (kraken,) = db.query(SegmentPass, document_id=doc.id)
    text = "\n".join(t for t in _texts_in_order(db, doc.id, kraken.id) if t)
    reading = Artifact(document_id=doc.id, artifact_type="transcription", content=text, model=TEACHER,
                       provider="openrouter")
    db.save(reading)
    return {"folder": folder, "doc": doc, "kraken": kraken, "text": text, "reading": reading}


def _run(client, db, page):
    r = client.post("/api/check/runs", json={"check": "tie-text-to-lines", "provider": "kraken", "model": READER,
                                             "layer": "readings", "scope_ids": [page["folder"].id],
                                             "pass_model": LINES})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    assert kind == "tie-text-to-lines"
    from fichero_server.checking import job as check_job

    check_job.register_job_kinds()
    # Claimed as the scheduler claims it, so a scheduler thread left by another test cannot run it too.
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ? AND state = 'waiting'", [job_id])
    jobs.KINDS[kind].run(db, subject)
    status = client.get(f"/api/check/runs/{job_id}")
    assert status.status_code == 200, status.text
    return job_id, status.json()


def _tied_pass(db, page):
    (made,) = [p for p in db.query(SegmentPass, document_id=page["doc"].id) if p.name == tie_text.TIED_NAME]
    return made


def _tied_in_source_order(db, page):
    """Each Kraken line, in the order the Kraken pass gives them: (its copy in the tied pass, the copy's text)."""
    import json

    from fichero_server.api.routes.document.segment_readings import counting_texts
    from fichero_server.checking.line_check import page_lines
    from fichero_server.page_export import export_page

    def key(row):
        return json.dumps(row.anchor.model_dump(mode="json"), sort_keys=True)

    source = {xml_id(s.id): s for s in db.query(Segment, pass_id=page["kraken"].id)}
    order = [ln["id"] for ln in page_lines(export_page(db, page["doc"].id, "pagexml",
                                                       pass_id=page["kraken"].id).data.decode("utf-8"))]
    copies = {key(s): s for s in db.query(Segment, pass_id=_tied_pass(db, page).id) if s.kind == "line"}
    rows = [copies[key(source[line_id])] for line_id in order]
    texts = counting_texts(db, rows)
    return [(row, texts.get(row.id, "")) for row in rows]


def _set(client, page):
    r = client.get("/api/training/set", params={"teacher": TEACHER, "scope_ids": [page["folder"].id]})
    assert r.status_code == 200, r.text
    return r.json()


def test_good_lines_are_tied_with_the_stretch_they_match_in_order(client, db, page, reader):
    """source.job.tie-text-to-lines: "Each line gets the stretch of the page reading it matches,
    automatically, wherever the alignment scores above the match threshold".
    WHY: this is the free teacher set: every Kraken line of a page read whole gets its own words, in the
    lines' order, with nothing for a person to do when the match is good."""
    _job_id, status = _run(client, db, page)
    expected = [t for t in _texts_in_order(db, page["doc"].id, page["kraken"].id) if t]
    assert status["counts"]["tied"] == len(expected) > 5
    assert status["counts"]["doubtful"] == 0 and status["flagged"] == []
    assert status["counts"]["pages_tied"] == 1
    tied = _tied_in_source_order(db, page)
    assert [text for _row, text in tied if text] == expected
    made = _tied_pass(db, page)
    derived = client.get(f"/api/segments/document/{page['doc'].id}/text", params={"pass_id": made.id}).json()
    in_text = [span["segment_id"] for span in derived["spans"]]
    assert in_text == [row.id for row, _text in tied if row.id in in_text] and len(in_text) > 5
    assert made.model == TEACHER and made.source_artifact_id == page["reading"].id


def test_a_doubtful_line_is_flagged_and_leaves_the_training_set(client, db, page, reader):
    """source.job.tie-text-to-lines (ruled 2026-10-04): "a line whose alignment is doubtful is flagged for
    review and counted, and stays out of the training set until a person checks it".
    WHY: a line whose page text and rough read disagree may be cut wrong; taught as it is, the student
    learns a line's picture with another line's words."""
    picked = {}

    def plan(lines):
        k = picked.setdefault("k", next(i for i in range(3, len(lines)) if len(lines[i]["text"]) >= 20))
        return {k: "q" * len(lines[k]["text"])}

    reader.plan = plan
    before = _set(client, page)
    assert before["lines"] == 0  # nothing the teacher read was on lines yet
    job_id, status = _run(client, db, page)
    (flag,) = status["flagged"]
    assert flag["flag"] == "doubtful: page text and line disagree" and flag["score"] < tie_text.THRESHOLD
    assert status["thresholds"]["tie"] == 0.30 and status["counts"]["doubtful"] == 1
    k_id = reader.lines[picked["k"]]["id"]
    copied = db.get(Segment, flag["segment_id"])
    source = {xml_id(s.id): s for s in db.query(Segment, pass_id=page["kraken"].id)}[k_id]
    assert copied.anchor == source.anchor  # the doubtful line is the one Kraken read badly
    (verdict,) = client.get("/api/check/verdicts", params={"target_id": flag["reading_id"]}).json()["items"]
    assert verdict["verdict"] == "reject" and verdict["trust"] == "model" and verdict["run_id"] == job_id
    after = _set(client, page)
    assert after["left_out"]["rejected"] == 1 and after["lines"] == status["counts"]["tied"]
    assert [x["segment_id"] for x in after["left_out_lines"] if x["flag"] == "rejected"] == [flag["segment_id"]]


def test_the_page_text_is_never_reordered(client, db, page, reader):
    """source.job.tie-text-to-lines: "aligned to them in order ... (a monotonic alignment; no line takes
    text from beyond its neighbours')".
    WHY: two rough reads swapped must not swap the page's words: the page text is the better reading, and
    its order is the page's. The swapped lines are flagged instead."""
    picked = {}

    def plan(lines):
        k = picked.setdefault("k", next(i for i in range(3, len(lines) - 1)
                                        if len(lines[i]["text"]) >= 20 and len(lines[i + 1]["text"]) >= 20))
        return {k: lines[k + 1]["text"], k + 1: lines[k]["text"]}

    reader.plan = plan
    _job_id, status = _run(client, db, page)
    tied = [text for _row, text in _tied_in_source_order(db, page)]
    assert " ".join(tied).split() == page["text"].split()
    assert status["counts"]["doubtful"] >= 1
    assert " ".join(tie_text.align("uno dos tres", ["tres", "uno dos"])).split() == ["uno", "dos", "tres"]


def test_the_readings_are_the_machines_never_a_persons(client, db, page, reader):
    """source.job.tie-text-to-lines: "The new pass names Kraken for the shapes and the page reading's model
    for the text."
    WHY: a tied line is a machine's guess at where the words go; stored as a person's it would count as
    checked ground truth and outrank a person's later reading."""
    job_id, _status = _run(client, db, page)
    made = _tied_pass(db, page)
    assert made.provenance_kind.value == "workflow" and made.run_id == job_id
    segments = [s for s in db.query(Segment, pass_id=made.id) if s.kind == "line"]
    readings = 0
    for segment in segments:
        items = client.get(f"/api/segments/{segment.id}/readings").json()["items"]
        for item in items:
            assert item["provenance_kind"] == "workflow" and item["derived_from_artifact_id"] == page["reading"].id
            readings += 1
    assert readings > 5


def test_running_twice_changes_nothing(client, db, page, reader):
    """WHY: a recipe re-run, or a person pressing again, must not stack a second pass of the same words on
    the page or a second verdict on a line."""
    reader.plan = lambda lines: {4: "q" * max(1, len(lines[4]["text"]))}
    _run(client, db, page)

    def snapshot():
        return (len(db.query(SegmentPass, document_id=page["doc"].id)), len(db.query(Segment)),
                len(db.query(ContentRepresentation)), len(db.query(CheckVerdict)))

    first = snapshot()
    _job_id, again = _run(client, db, page)
    assert snapshot() == first
    assert again["counts"]["already_tied"] == 1 and again["counts"]["pages_tied"] == 0


def test_the_tie_is_a_job_on_the_local_model_lane(client, db, page, reader):
    """source.check.run-is-a-job: one row in Activity, named as the recipe job.
    WHY: Kraken loads a reader on this Mac; on the remote lane it could run beside another heavy model."""
    _job_id, status = _run(client, db, page)
    assert jobs.KINDS["tie-text-to-lines"].lane == "local-ml"
    assert status["reason"].startswith(f"{status['counts']['tied']} lines tied")


def test_the_tie_refuses_a_layer_or_reader_it_cannot_use(client, db, page, reader):
    """WHY: a tie of statements, or with a cloud model as the rough reader, would queue a job that can only
    fail; it is refused when asked."""
    for bad in ({"layer": "claims"}, {"provider": "openrouter"}):
        body = {"check": "tie-text-to-lines", "provider": "kraken", "model": READER, "layer": "readings",
                "scope_ids": [page["folder"].id], **bad}
        assert client.post("/api/check/runs", json=body).status_code == 422


def test_the_alignment_gives_each_line_its_stretch():
    """The aligner alone: case, accents and spacing do not decide where a line ends.
    WHY: a rough read that is close but not exact must still find its own words, and a line Kraken read
    as nothing gets nothing from its neighbours."""
    page = "Él dicho escribano\nvecino de la ciudad y lo firmó"
    assert tie_text.align(page, ["el dicho escrivano", "vezino de la cuidad", "y lo firmo"]) == [
        "Él dicho escribano", "vecino de la ciudad", "y lo firmó"]
    scored = tie_text.tie_lines(page, ["el dicho escrivano", "xxxxxxxxxxxxxxxxxx", "y lo firmo"])
    assert [s["tied"] for s in scored] == [True, False, True]
    assert scored[1]["text"] == "vecino de la ciudad"
