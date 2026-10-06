"""Which machine reading of a line counts after the page text is tied to it, and the tie after every page
reading (#5558, residue of #5444/#5487).

`source.reading.machine-ranked-by-measure` (readings-and-apparatus.md) and `source.job.tie-text-to-lines`
(models-chains-and-projects.md): an older reading never counts while a better one exists. Among machine
readings: a checked one (a person confirmed it, or it was tied from a page reading a person confirmed or
marked reviewed), then the one whose reader measured better ON THIS PROJECT (the evaluation entries on the
model's card scored on this project's pages: the bake-off), then the newest; the date only breaks ties. A
reader never measured here is never ranked by a score (cloud readers cannot be measured yet: the evaluation
has no remote target). With no scores, the newest counts, as before.

Everything runs through the real paths: the tie job as the scheduler runs it (`POST /api/check/runs`), a
Kraken re-read written onto the page's lines as `vision_base` writes it (`working_lines.write_readings`,
derived from a Kraken page artifact), scores written on the cards by `evaluation.record_on_card`, the
counting answer as the page's text and segment lists read it (`counting_texts`, `GET /api/segments/
document/{id}/text`), the training set as `build_training_set` writes it, and a page reading saved through
`llm_base.save_file_artifact`. Kraken is faked at its seams; nothing is trained, downloaded or sent.
"""
# ruff: noqa: F811  (the tie tests' `page` and `reader` fixtures are imported and named as arguments)
from __future__ import annotations

import asyncio
import json

import pytest

from fichero_server.checking import tie_text
from fichero_server.execution import jobs
from fichero_server.llm import kraken_runtime
from fichero_server.llm.working_lines import READ_ONTO_PASS, write_readings
from fichero_server.models import Artifact, DocType, Document
from fichero_server.models.checking import CheckVerdict
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.readings import ProjectRecordRule, ReadingCandidate, resolve_counting
from fichero_server.training import evaluation
from tests.unit.check.test_tie_text_to_lines import (  # noqa: F401  (pytest fixtures)
    READER,
    _counting,
    _lines,
    _run,
    _tied,
    page,
    reader,
)
from tests.unit.training.test_kraken_training_set import TEACHER, _page

STOCK = READER  # the stock Kraken reader that re-reads the lines roughly


@pytest.fixture(autouse=True)
def _own_model_stores(tmp_path, monkeypatch):
    """The cards (where scores live) and Kraken's install markers in this test's own folders."""
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "models"))
    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken"))


def _install(model: str) -> None:
    marker = kraken_runtime._marker_path(model)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"model_path": "/models/mccatmus.mlmodel"}), encoding="utf-8")


def _measure(db, page, model: str, reader_kind: str, *, damage: int) -> None:
    """The reader scored on this project's page, as the evaluation job writes it on the model's card: each
    line read with its last `damage` characters wrong."""
    reference = [t for t in page["before"] if t.strip()]
    reads = [t[:-damage] + "#" * damage if damage else t for t in reference]
    per_page = [{"document_id": page["doc"].id, "name": page["doc"].name, "trust": "person",
                 "lines": len(reference), "scores": evaluation.score_page(reference, reads)}]
    evaluation.record_on_card(model, reader_kind, {"job_id": f"bakeoff-{model}", "pages": [page["doc"].id],
                                                   "per_page": per_page})


def _reread(db, page) -> Artifact:
    """Stock Kraken reads the page's own lines again, roughly, and its words are written onto them as
    `vision_base` writes a read onto the working pass (#5487)."""
    lines = _lines(db, page["kraken"].id)
    rough = [f"rough {i}" for i in range(len(lines))]
    artifact = Artifact(document_id=page["doc"].id, artifact_type="transcription", content="\n".join(rough),
                        provider="kraken", model=STOCK, data={READ_ONTO_PASS: page["kraken"].id})
    db.save(artifact)
    write_readings(db, document_id=page["doc"].id, readings=list(zip([r.id for r in lines], rough)),
                   artifact_id=artifact.id, run_id=f"read-a-line:{artifact.id}")
    return artifact


def _tied_texts(db, page) -> list[str]:
    return [r.content if r else "" for _row, r in _tied(db, page)]


def _training_set_texts(db, page, tmp_path) -> list[str]:
    """The lines' texts in the teacher's training set, read back out of the PAGE XML it wrote: each line's
    counting reading, the TextEquiv `page_export` writes first (index 0); the others are alternatives."""
    from fichero_server.formats.pagexml import PAGE_NS_2019
    from fichero_server.security.xml_security import parse_xml_string
    from fichero_server.training.kraken_set import build_training_set

    out = tmp_path / "set"
    built = build_training_set(db, scope_ids=[page["folder"].id], teacher=TEACHER, held_out_ids=[], out_dir=out)
    (written,) = built.pages
    root = parse_xml_string((out / written.xml).read_text(encoding="utf-8"))
    ns = f"{{{PAGE_NS_2019}}}"
    texts = []
    for line in root.iter(f"{ns}TextLine"):  # the line's first TextEquiv (index 0) is the reading that counts
        first = next((e for e in line.findall(f"{ns}TextEquiv") if e.get("index") == "0"), None)
        texts.append("" if first is None else "".join(u.text or "" for u in first.iter(f"{ns}Unicode")))
    return texts


# --- the rule alone ----------------------------------------------------------------------------------------


def _machine(rid: str, minute: int, **extra) -> ReadingCandidate:
    from datetime import datetime, timezone

    return ReadingCandidate(representation_id=rid, kind="transcription", provenance_kind=ProvenanceKind.workflow,
                            created_at=datetime(2026, 10, 6, 12, minute, tzinfo=timezone.utc), **extra)


@pytest.mark.parametrize("rule", list(ProjectRecordRule))
def test_the_rule_ranks_checked_then_measured_then_newest(rule):
    """source.reading.machine-ranked-by-measure: checked, then the better measured reader, then the newest.
    WHY: a rough re-read made after a good reading must not become the record just by being newer."""
    def counts(*rows):
        return resolve_counting(rule, [], list(rows)).representation_id

    assert counts(_machine("old", 1), _machine("new", 2)) == "new"  # no measures: newest, as before
    assert counts(_machine("good", 1, reader_cer=0.05), _machine("rough", 2, reader_cer=0.40)) == "good"
    assert counts(_machine("good", 1, reader_cer=0.050), _machine("tie", 2, reader_cer=0.055)) == "tie"  # one point
    assert counts(_machine("unmeasured", 1), _machine("rough", 2, reader_cer=0.40)) == "rough"  # never invented
    assert counts(_machine("unmeasured", 2), _machine("good", 1, reader_cer=0.05)) == "unmeasured"
    assert counts(_machine("checked", 1, checked=True, reader_cer=0.5), _machine("good", 2, reader_cer=0.01)) == "checked"
    answer = resolve_counting(rule, [], [_machine("good", 1, reader_cer=0.05), _machine("rough", 2, reader_cer=0.4)])
    assert answer.labelled_machine and answer.basis.value == "newest-machine-unchosen"


# --- through the engine ------------------------------------------------------------------------------------


def test_a_rough_kraken_reread_does_not_displace_the_tied_stretch_of_a_better_reader(client, db, page, reader,
                                                                                    tmp_path):
    """source.reading.machine-ranked-by-measure (#5558): "tie a cloud page reading, re-read with stock Kraken
    (measured worse on the project): the tied stretch still counts", and the training set carries the
    teacher's reading because it counts.
    WHY: on Mosquera a Kraken re-read after the tie replaced Gemini's good lines with rough ones, in the
    Source view, the export and the set a student model is trained on."""
    _run(client, db, page)
    tied = _tied_texts(db, page)
    assert sum(bool(t) for t in tied) > 5
    _measure(db, page, TEACHER, "vision", damage=0)
    _measure(db, page, STOCK, "kraken", damage=6)
    _reread(db, page)
    lines = _lines(db, page["kraken"].id)
    assert _counting(db, lines) == tied
    derived = client.get(f"/api/segments/document/{page['doc'].id}/text", params={"pass_id": page["kraken"].id})
    assert "rough" not in derived.json()["text"]
    assert [t for t in _training_set_texts(db, page, tmp_path) if t] == [t for t in tied if t]


def test_with_no_scores_the_newest_machine_reading_still_counts(client, db, page, reader, tmp_path):
    """source.reading.machine-ranked-by-measure: "with no scores at all, the newest counts, as before".
    WHY: the date is still the answer wherever nothing was measured; the rule adds evidence, not a guess."""
    _run(client, db, page)
    _reread(db, page)
    lines = _lines(db, page["kraken"].id)
    assert _counting(db, lines) == [f"rough {i}" for i in range(len(lines))]


def test_a_reader_measured_alone_is_not_ranked_against_one_never_measured(client, db, page, reader):
    """source.reading.machine-ranked-by-measure: only measured readers are compared; a score is never
    invented for a reader the project never measured (a cloud reader cannot be measured yet).
    WHY: treating "not measured" as best or worst would let the rule decide on a number nobody took."""
    _run(client, db, page)
    _measure(db, page, STOCK, "kraken", damage=6)  # the cloud teacher is not measured
    _reread(db, page)
    lines = _lines(db, page["kraken"].id)
    assert _counting(db, lines) == [f"rough {i}" for i in range(len(lines))]


def test_a_score_from_another_project_is_not_this_projects(client, db, page, reader):
    """source.reading.machine-ranked-by-measure: the score is the reader's measured CER on THIS project.
    WHY: a card is this Mac's, shared by every project; a reader good on one archive's hand may be poor on
    another's, so only an evaluation on this project's own pages ranks its readings."""
    _run(client, db, page)
    _measure(db, page, STOCK, "kraken", damage=6)
    evaluation.record_on_card(TEACHER, "vision", {"pages": ["a-page-of-another-project"], "per_page": [
        {"document_id": "a-page-of-another-project", "name": "x", "lines": 1,
         "scores": evaluation.score_page(["uno"], ["uno"])}]})
    assert evaluation.measured_here(db, TEACHER, "vision") is None
    assert evaluation.measured_here(db, STOCK, "kraken") > 0.1


@pytest.mark.parametrize("how", ["reviewed", "confirmed"])
def test_mosquera_a_checked_cloud_page_reading_keeps_its_tied_lines(client, db, page, reader, tmp_path, how):
    """source.reading.machine-ranked-by-measure (#5558, the Mosquera case): a cloud page reading a person
    confirmed or marked reviewed is tied to the lines; stock Kraken (measured on the project; the cloud
    reader cannot be) re-reads them; the tied stretches still count, in the page and in the training set.
    WHY: a person's check of the page text is the strongest evidence there is that it is the better reading."""
    if how == "reviewed":  # Mark Reviewed on the page reading (the Inspector's artifact edit)
        r = client.put(f"/api/artifacts/{page['reading'].id}", json={"reviewed": True})
        assert r.status_code == 200, r.text
    else:  # a person's confirm verdict on the page reading, the one `tie_text.page_reading` reads
        # (stored directly: `check.verdict` takes a reading's id, not a page artifact's, today)
        db.save(CheckVerdict(layer="readings", target_id=page["reading"].id, document_id=page["doc"].id,
                             verdict="confirm", reasons="read against the page", checker="owner", trust="person"))
    _run(client, db, page)
    tied = _tied_texts(db, page)
    _measure(db, page, STOCK, "kraken", damage=0)  # even measured perfect, an unchecked rough read ranks below
    _reread(db, page)
    assert _counting(db, _lines(db, page["kraken"].id)) == tied
    assert [t for t in _training_set_texts(db, page, tmp_path) if t] == [t for t in tied if t]


def test_a_doubtful_tied_stretch_does_not_inherit_its_page_readings_check(client, db, page, reader):
    """source.reading.machine-ranked-by-measure: a tied stretch the tie flagged doubtful (its own reject)
    is not checked by its page reading's confirmation.
    WHY: the person confirmed the page text, not where the tie cut it; a doubtful cut stays doubtful."""
    page["reading"].reviewed = True
    db.save(page["reading"])
    reader.plan = lambda lines: {4: "q" * max(1, len(lines[4]["text"]))}
    _job, status = _run(client, db, page)
    (flag,) = status["flagged"]
    _reread(db, page)
    texts = dict(zip([r.id for r in _lines(db, page["kraken"].id)], _counting(db, _lines(db, page["kraken"].id))))
    assert texts[flag["segment_id"]].startswith("rough ")
    assert sum(not t.startswith("rough ") for t in texts.values() if t) > 5


def test_a_person_confirming_the_reread_makes_it_count(client, db, page, reader):
    """source.reading.machine-ranked-by-measure: a machine reading a person confirmed outranks unchecked ones.
    WHY: where the rough read is in fact right, a person's confirmation is the answer, whatever was measured."""
    _run(client, db, page)
    _measure(db, page, TEACHER, "vision", damage=0)
    _measure(db, page, STOCK, "kraken", damage=6)
    _reread(db, page)
    line = _lines(db, page["kraken"].id)[2]
    from fichero_server.api.routes.document.segment_readings import readings_of_segment

    (rough,) = [r for r in readings_of_segment(db, line.id) if r.content.startswith("rough ")]
    r = client.post("/api/check/verdicts", json={"layer": "readings", "target_id": rough.id, "verdict": "confirm",
                                                 "reasons": "the rough read is right here", "segment_id": line.id})
    assert r.status_code == 200, r.text
    assert _counting(db, [line]) == [rough.content]


# --- the tie after every page reading ----------------------------------------------------------------------


def _save_page_reading(db, doc, text):
    """A page reading saved as every reader's result is saved (`llm_base.save_file_artifact`)."""
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.llm_base import LLMToolConfig, save_file_artifact

    return asyncio.run(save_file_artifact(
        None, text, doc.id, str(db.path.parent), LLMConfig(provider="openrouter", model=TEACHER), "run-read",
        LLMToolConfig(artifact_type="transcription"), document=db.get(Document, doc.id)))


def _tie_jobs(db):
    return db.execute_fetchall("SELECT id, subject, state, started_by FROM jobs WHERE kind = ?", [tie_text.KIND])


def test_a_page_reading_on_a_page_with_lines_queues_its_tie(client, db, page, reader):
    """source.job.tie-text-to-lines (#5558): "the tie runs after every page reading, no recipe step needed"
    -- as background work, one waiting job per page, on the local model lane, and it ties the lines.
    WHY: 319 of 374 Mosquera pages had Gemini's page reading and no line carrying it, because nothing tied
    them unless a recipe named the step."""
    _install(READER)
    from fichero_server.db import db_manager

    assert db_manager.get_database(str(db.path.parent)) is db
    _save_page_reading(db, page["doc"], page["text"])
    artifact_id = _save_page_reading(db, page["doc"], page["text"])  # a second reading: still one waiting tie
    ((job_id, subject, state, started_by),) = _tie_jobs(db)
    assert state == "waiting" and started_by == tie_text.AUTOMATIC
    assert _tied_texts(db, page) == [""] * len(_lines(db, page["kraken"].id))  # nothing ran inline
    assert jobs.KINDS[tie_text.KIND].lane == "local-ml"
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [job_id])
    result = jobs.KINDS[tie_text.KIND].run(db, subject)
    assert result["counts"]["tied"] > 5
    assert tie_text.page_reading(db, page["doc"].id).id == artifact_id  # the newest page reading is tied
    assert sum(bool(r) for _row, r in _tied(db, page, artifact_id)) == result["counts"]["tied"]


def test_a_page_without_lines_or_without_a_kraken_reader_queues_no_tie(client, db, page, reader, tmp_path):
    """source.job.tie-text-to-lines (#5558): a page without lines gets no tie (its lines are found by the
    reading step itself), and nor does a reading of the lines' own text or a Mac with no Kraken reader.
    WHY: a tie that can only fail, or that ties a rough read to itself, is work nobody asked for."""
    _save_page_reading(db, page["doc"], page["text"])
    assert _tie_jobs(db) == []  # no Kraken reader on this Mac
    _install(READER)
    folder = Document(name="SM_NPQ_C03", doc_type=DocType.folder)
    db.save(folder)
    bare = _page(db, tmp_path, "SM_NPQ_C03_001", folder, read_by=None, size=(400, 300))
    _save_page_reading(db, bare, "uno dos\ntres cuatro")
    assert _tie_jobs(db) == []
    own = Artifact(document_id=page["doc"].id, artifact_type="transcription", content="x", provider="kraken",
                   model=READER, data={READ_ONTO_PASS: page["kraken"].id})
    assert tie_text.after_page_reading(db, own) is None
    assert db.query(CheckVerdict) == []
