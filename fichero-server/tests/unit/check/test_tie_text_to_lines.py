"""`source.job.tie-text-to-lines` (#5444), tested to the spec through the public routes.

A page read whole by a model has good text and no lines; Kraken found the lines and reads each roughly.
The page text is aligned in order to the rough reads and each line gets the stretch it matches: tied
automatically where the stretch agrees with the line's rough read above the threshold, flagged for review
(and kept out of the training set) below it (ruled 2026-10-04). The stretches are readings on the page's
OWN lines, never a second pass (one line pass per page, read many times, #5487, ruled 2026-10-05).

Everything goes through `POST /api/check/runs` (check `tie-text-to-lines`), the job as the scheduler runs
it (`jobs.KINDS["tie-text-to-lines"].run`), `GET /api/check/runs/{id}`, `/api/check/verdicts`,
`GET /api/segments/{id}/readings` and `GET /api/training/set`. Kraken is faked at its seams
(`kraken_runtime.read_given_lines`, `segment_lines`): no torch, no model, no training.
"""
from __future__ import annotations

import pytest

from fichero_server.checking import tie_text
from fichero_server.execution import jobs
from fichero_server.llm import kraken_runtime
from fichero_server.models import Artifact, ContentRepresentation, DocType, Document, Segment
from fichero_server.models.checking import CheckVerdict
from fichero_server.models.segments import SegmentPass
from tests.unit.training.test_kraken_training_set import TEACHER, _page

READER = "kraken-mccatmus"
LINES = "kraken-blla"


def _counting(db, rows):
    from fichero_server.api.routes.document.segment_readings import counting_texts

    texts = counting_texts(db, rows)
    return [texts.get(row.id, "") for row in rows]


class RoughReader:
    """Kraken's reader, faked at the seam: each line reads as the text it carries before the tie, unless the
    test says otherwise."""

    def __init__(self, db):
        self.db = db
        self.lines: list[dict] = []
        self.plan = lambda lines: {}

    def __call__(self, image_path, model_path, lines, **kw):
        assert model_path == "/models/mccatmus.mlmodel"
        rows = [self.db.get(Segment, line["id"]) for line in lines]
        self.lines = [{**line, "text": text} for line, text in zip(lines, _counting(self.db, rows))]
        override = self.plan(self.lines)
        return [override.get(i, line["text"]) for i, line in enumerate(self.lines)]


@pytest.fixture
def reader(db, monkeypatch):
    fake = RoughReader(db)
    monkeypatch.setattr(kraken_runtime, "read_given_lines", fake)
    monkeypatch.setattr(kraken_runtime, "resolve_recognition_model", lambda ref: ("/models/mccatmus.mlmodel", ref))
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)  # the test runs the job itself
    return fake


def _lines(db, pass_id):
    from fichero_server.api.routes.document.segment_readings import ordered_lines

    return ordered_lines(db, pass_id)


@pytest.fixture
def page(db, tmp_path):
    """A page whose lines Kraken found (the imported pass, marked as Kraken's) and whose text the teacher
    read whole: the page reading is the lines' texts, one after another, as one transcription."""
    folder = Document(name="SM_NPQ_C01", doc_type=DocType.folder)
    db.save(folder)
    doc = _page(db, tmp_path, "SM_NPQ_C01_001", folder, read_by=LINES, size=(274, 396))
    (kraken,) = db.query(SegmentPass, document_id=doc.id)
    before = _counting(db, _lines(db, kraken.id))
    text = "\n".join(t for t in before if t)
    reading = Artifact(document_id=doc.id, artifact_type="transcription", content=text, model=TEACHER,
                       provider="openrouter")
    db.save(reading)
    return {"folder": folder, "doc": doc, "kraken": kraken, "text": text, "reading": reading, "before": before}


def _run(client, db, page, **extra):
    body = {"check": "tie-text-to-lines", "provider": "kraken", "model": READER, "layer": "readings",
            "scope_ids": [page["folder"].id], **extra}
    r = client.post("/api/check/runs", json=body)
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


def _tied(db, page, reading_id=None):
    """Each of the page's lines, in its order, and the reading the tie gave it (None for a line left untied)."""
    from fichero_server.api.routes.document.segment_readings import readings_of_segment

    reading_id = reading_id or page["reading"].id
    out = []
    for row in _lines(db, page["kraken"].id):
        made = [r for r in readings_of_segment(db, row.id) if r.derived_from_artifact_id == reading_id]
        assert len(made) <= 1
        out.append((row, made[0] if made else None))
    return out


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
    expected = [t.strip() for t in page["before"] if t.strip()]
    assert status["counts"]["tied"] == len(expected) > 5
    assert status["counts"]["doubtful"] == 0 and status["flagged"] == []
    assert status["counts"]["pages_tied"] == 1
    tied = _tied(db, page)
    assert [r.content for _row, r in tied if r] == expected
    # The stretch is the line's counting reading, and the page's text reads the page's own lines.
    lines = [row for row, _r in tied]
    assert [t for t in _counting(db, lines) if t] == expected
    derived = client.get(f"/api/segments/document/{page['doc'].id}/text",
                         params={"pass_id": page["kraken"].id}).json()
    in_text = [span["segment_id"] for span in derived["spans"]]
    assert in_text == [row.id for row, r in tied if r and row.id in in_text] and len(in_text) > 5


def test_the_tie_writes_onto_the_pages_lines_and_never_makes_a_second_pass(client, db, page, reader):
    """source-model.md "Every output comes into the page" (#5467, #5487): "One line pass per page, read many
    times ... they never make a second line pass".
    WHY: a second pass of copied lines left the page with two sets of the same lines, and the Source view,
    the Segments list and the export could each show a different one."""
    passes_before = [p.id for p in db.query(SegmentPass, document_id=page["doc"].id)]
    segments_before = len(db.query(Segment))
    _run(client, db, page)
    assert [p.id for p in db.query(SegmentPass, document_id=page["doc"].id)] == passes_before
    assert len(db.query(Segment)) == segments_before


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
    assert flag["segment_id"] == reader.lines[picked["k"]]["id"]  # the doubtful line is the one Kraken read badly
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
    tied = [r.content for _row, r in _tied(db, page) if r]
    assert " ".join(tied).split() == page["text"].split()
    assert status["counts"]["doubtful"] >= 1
    assert " ".join(tie_text.align("uno dos tres", ["tres", "uno dos"])).split() == ["uno", "dos", "tres"]


def test_the_readings_are_the_machines_never_a_persons(client, db, page, reader):
    """source.job.tie-text-to-lines: the shapes stay Kraken's and the text names "the page reading's model".
    WHY: a tied line is a machine's guess at where the words go; stored as a person's it would count as
    checked ground truth and outrank a person's later reading."""
    _run(client, db, page)
    readings = 0
    for row, _r in _tied(db, page):
        items = client.get(f"/api/segments/{row.id}/readings").json()["items"]
        for item in items:
            if item["derived_from_artifact_id"] == page["reading"].id:
                assert item["provenance_kind"] == "workflow"
                readings += 1
    assert readings > 5


def test_running_twice_changes_nothing(client, db, page, reader):
    """WHY: a recipe re-run, or a person pressing again, must not stack a second copy of the same words on
    the lines or a second verdict on a line."""
    reader.plan = lambda lines: {4: "q" * max(1, len(lines[4]["text"]))}
    _run(client, db, page)

    def snapshot():
        return (len(db.query(SegmentPass, document_id=page["doc"].id)), len(db.query(Segment)),
                len(db.query(ContentRepresentation)), len(db.query(CheckVerdict)))

    first = snapshot()
    _job_id, again = _run(client, db, page)
    assert snapshot() == first
    assert again["counts"]["already_tied"] == 1 and again["counts"]["pages_tied"] == 0


def test_the_page_reading_tied_is_the_best_never_the_lines_own_read(client, db, page, reader):
    """source.job.tie-text-to-lines: "The page's best reading is, in order: a person's checked reading, a
    checked model reading, then the newest model page reading." (#5444, 2026-10-06: on the Fable-checked
    pages the newest transcription was Kraken's own read, so the tie made a rough read its own reference.)
    WHY: the page text tied to the lines becomes their ground truth for training and evaluation."""
    from fichero_server.llm.working_lines import READ_ONTO_PASS

    newer_rough = Artifact(document_id=page["doc"].id, artifact_type="transcription", content="tal cual",
                           model=READER, provider="kraken", data={READ_ONTO_PASS: page["kraken"].id})
    db.save(newer_rough)
    assert tie_text.page_reading(db, page["doc"].id).id == page["reading"].id
    checked = Artifact(document_id=page["doc"].id, artifact_type="transcription", content=page["text"],
                       model="fable", provider="openrouter", reviewed=True,
                       created_at=page["reading"].created_at.replace(year=2001))
    db.save(checked)
    assert tie_text.page_reading(db, page["doc"].id).id == checked.id  # checked beats newer
    persons = Artifact(document_id=page["doc"].id, artifact_type="transcription", content=page["text"],
                       provider="human", created_at=page["reading"].created_at.replace(year=2000))
    db.save(persons)
    assert tie_text.page_reading(db, page["doc"].id).id == persons.id  # a person's beats every model's
    _run(client, db, page)
    assert all(r is None or r.derived_from_artifact_id == persons.id for _row, r in _tied(db, page, persons.id))
    assert any(r for _row, r in _tied(db, page, persons.id))


def test_a_page_with_no_lines_has_them_found_by_kraken_first(client, db, tmp_path, reader, monkeypatch):
    """source.job.tie-text-to-lines: "Kraken finds the lines, a Kraken reader reads each roughly" (#5444:
    319 of 374 Mosquera pages had Gemini's page reading and no line carrying it).
    WHY: the tie is free and local only if it needs nothing but the photograph and the page text."""
    folder = Document(name="SM_NPQ_C02", doc_type=DocType.folder)
    db.save(folder)
    doc = _page(db, tmp_path, "SM_NPQ_C02_001", folder, read_by=None, size=(400, 300))
    db.save(Artifact(document_id=doc.id, artifact_type="transcription", content="uno dos\ntres cuatro",
                     model=TEACHER, provider="openrouter"))
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda image_path, **kw: {
        "width": 400, "height": 300,
        "regions": [{"id": "r1", "type": "text", "polygon": [[5, 5], [395, 5], [395, 200], [5, 200]]}],
        "lines": [{"baseline": [[10, 50], [390, 50]], "polygon": [[10, 20], [390, 20], [390, 60], [10, 60]],
                   "region": "r1"},
                  {"baseline": [[10, 150], [390, 150]], "polygon": [[10, 120], [390, 120], [390, 160], [10, 160]],
                   "region": "r1"}]})
    reader.plan = lambda lines: {0: "uno dos", 1: "tres cuatro"}
    _job_id, status = _run(client, db, {"folder": folder})
    assert status["counts"]["lines_found"] == 1 and status["counts"]["tied"] == 2
    (made,) = db.query(SegmentPass, document_id=doc.id)
    lines = _lines(db, made.id)
    assert _counting(db, lines) == ["uno dos", "tres cuatro"]
    (region,) = [s for s in db.query(Segment, pass_id=made.id) if s.kind == "region"]
    assert {line.parent_segment_id for line in lines} == {region.id}


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
