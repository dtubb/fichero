"""Imported corrected transcriptions as ground truth (#5513, part of #5499), tested to the spec.

`source/models-chains-and-projects.md` section 7: "Corrected transcriptions given at setup come in through
the one import path as person-made passes marked as ground truth"; `source.onboard.ground-truth-from-files`
("... and the bake-off uses them"); `source.onboard.bakeoff-minimum` (below the threshold it says how many
more are needed). Found on a corpus run: 9 projects, 4,344 imported ground-truth lines, every bake-off "0 on
0 pages", the readings labelled machine.

The mark is one fact on the pass (`SegmentPass.ground_truth`), set at import (`ground_truth` on the import
routes) or afterwards (`PUT /api/segments/passes/{id}/ground-truth`, audited, undoable). Who MADE the pass
stays the file (`external_import`); every rule that asks "did a person make it?" reads both through
`made_by_a_person`. Everything goes through the routes the app and the CLI use.
"""
from __future__ import annotations

import pytest

from fichero_server.models import ActionAudit, ContentRepresentation, DocType, Document, Segment
from fichero_server.models.segments import SegmentPass
from fichero_server.recipes import bakeoff
from fichero_server.training import evaluation
from tests.unit.recipes.test_bakeoff_readers import _set_up
from tests.unit.training.test_kraken_training_set import PAGE, _page

LINES = 44  # the corpus fixture's PAGE file: a Transkribus export of a Spanish notarial page


@pytest.fixture
def folder(db):
    made = Document(name="SM_NPQ_C01", doc_type=DocType.folder)
    db.save(made)
    return made


def _import(client, doc: Document, **query) -> dict:
    """The one-file import the app's menu uses, with the person's answer to "are these corrected?"."""
    with PAGE.open("rb") as fh:
        r = client.post(f"/api/documents/{doc.id}/import", params=query,
                        files={"file": (PAGE.name, fh, "application/xml")})
    assert r.status_code == 200, r.text
    return r.json()


def _readiness(client) -> dict:
    r = client.get("/api/recipes/project/bakeoffs")
    assert r.status_code == 200, r.text
    return r.json()["readiness"]


def _first_line(db, pass_id: str) -> Segment:
    lines = [s for s in db.query(Segment, pass_id=pass_id) if s.kind == "line"]
    return min(lines, key=lambda s: s.metadata.get("file_position", 0))


def test_an_import_marked_ground_truth_counts_for_the_bakeoff(client, db, tmp_path, folder):
    """source.onboard.ground-truth-from-files: corrected transcriptions "come in through the one import path
    as person-made passes marked ground truth, and the bake-off uses them".
    WHY: a corpus project's ground truth IS its imported PAGE files; if the bake-off counts only passes a
    person drew in Fichero, a project with thousands of corrected lines reads "0 on 0 pages"."""
    page = _page(db, tmp_path, "SM_NPQ_C01_001", folder, read_by=None)
    made = _import(client, page, ground_truth="true")
    assert made["ground_truth"] is True

    pass_row = db.get(SegmentPass, made["pass_id"])
    # The file still made it: the mark is who VOUCHES, not a rewrite of who made it (#5150).
    assert pass_row.ground_truth and getattr(pass_row.provenance_kind, "value", None) == "external_import"
    passes = client.get(f"/api/segments/document/{page.id}").json()["passes"]
    assert next(p for p in passes if p["id"] == made["pass_id"])["ground_truth"] is True

    ready = _readiness(client)
    assert (ready["lines"], ready["pages"], ready["unmarked_import_pages"]) == (LINES, 1, 0)
    assert ready["sentence"] == (f"Needs 100 corrected lines on at least 2 pages; this project has {LINES} on 1 page. "
                                 f"Correct {100 - LINES} more lines, on at least 1 more page.")


def test_an_unmarked_import_does_not_count_and_the_sentence_says_how_to_mark_it(client, db, tmp_path, folder):
    """source.onboard.bakeoff-minimum: below the threshold "it says how many more are needed", in words.
    WHY: a file of unknown origin is often a machine's (Transkribus HTR), so an import is not ground truth
    until a person says so; but a person whose corrected files count for nothing must be told WHY and what to
    do, in one plain sentence, not "Correct 100 more corrected lines and corrected lines on 2 more pages"."""
    _set_up(client)
    for name in ("SM_NPQ_C01_001", "SM_NPQ_C01_002"):
        _import(client, _page(db, tmp_path, name, folder, read_by=None))

    ready = _readiness(client)
    assert (ready["ready"], ready["lines"], ready["pages"], ready["unmarked_import_pages"]) == (False, 0, 0, 2)
    assert ready["sentence"] == (
        "Needs 100 corrected lines on at least 2 pages; this project has 0 on 0 pages. 2 pages have imported "
        "transcriptions not marked as ground truth: mark the corrected ones as ground truth (Mark as Ground "
        "Truth on the pass), or correct more lines.")
    refused = client.post("/api/recipes/project/bakeoffs", json={})
    assert refused.status_code == 422 and refused.json()["detail"] == ready["sentence"]


def test_the_sentence_without_imports_is_plain_and_correct():
    """WHY: the old sentence joined two shortfalls into "Correct 56 more corrected lines and corrected lines on
    1 more page"; each case must read as plain English with the right numbers and plurals."""
    def said(lines_per_page: list[int]) -> str:
        return bakeoff.readiness([{"lines": n} for n in lines_per_page])["sentence"]

    assert said([]) == ("Needs 100 corrected lines on at least 2 pages; this project has 0 on 0 pages. "
                        "Correct 100 more lines, on at least 2 more pages.")
    assert said([150]) == ("Needs 100 corrected lines on at least 2 pages; this project has 150 on 1 page. "
                           "Correct lines on 1 more page.")
    assert said([44, 55]) == ("Needs 100 corrected lines on at least 2 pages; this project has 99 on 2 pages. "
                              "Correct 1 more line.")
    assert bakeoff.readiness([{"lines": 50}, {"lines": 50}])["sentence"] is None


def test_marking_afterwards_is_audited_and_undo_unmarks(client, db, tmp_path, folder):
    """The corpus projects are already imported: marking must be possible afterwards, as an audited action
    (one audited action layer) that ⌘Z takes back.
    WHY: marking decides what a model is scored against; a mark nobody can see the author of, or cannot
    take back, would let a mistaken click set every later score."""
    page = _page(db, tmp_path, "SM_NPQ_C01_001", folder, read_by=None)
    made = _import(client, page)
    assert _readiness(client)["lines"] == 0

    marked = client.put(f"/api/segments/passes/{made['pass_id']}/ground-truth", json={"ground_truth": True})
    assert marked.status_code == 200, marked.text
    assert marked.json() == {"pass_id": made["pass_id"], "ground_truth": True}
    assert (_readiness(client)["lines"], _readiness(client)["unmarked_import_pages"]) == (LINES, 0)

    (audit,) = [a for a in db.query(ActionAudit) if a.action_name == "segment.pass_ground_truth"]
    assert audit.actor
    assert client.post(f"/api/actions/audit/{audit.id}/undo").status_code == 200
    assert db.get(SegmentPass, made["pass_id"]).ground_truth is False
    assert (_readiness(client)["lines"], _readiness(client)["unmarked_import_pages"]) == (0, 1)

    missing = client.put("/api/segments/passes/nope/ground-truth", json={"ground_truth": True})
    assert missing.status_code == 404


def test_the_evaluation_takes_the_marked_pass_as_its_reference(client, db, tmp_path, folder):
    """`distill.eval.*`: with no `checked` named, the reference is "the pass a person made" -- and a pass a
    person marked ground truth is one (#5513), checked by a person.
    WHY: the bake-off IS the evaluation job; if the two chose references differently, readiness would count
    pages the job then scores against nothing."""
    page = _page(db, tmp_path, "SM_NPQ_C01_001", folder, read_by=None)
    unmarked = _import(client, page)
    assert evaluation.reference_page(db, page.id, None) == (None, "no pass made by a person")

    client.put(f"/api/segments/passes/{unmarked['pass_id']}/ground-truth", json={"ground_truth": True})
    reference, why = evaluation.reference_page(db, page.id, None)
    assert why is None
    assert (reference["pass_id"], reference["trust"], len(reference["lines"])) == (unmarked["pass_id"], "person", LINES)


def test_the_readings_of_a_marked_pass_are_not_called_machine(client, db, tmp_path, folder):
    """`source.reading.machine-is-labelled`: a machine's reading is labelled. A file's reading a person marked
    ground truth is not a machine's guess.
    WHY: the corpus run found the imported ground truth labelled `labelled_machine: true`, so the Reader
    showed a historian's corrected edition as unreviewed machine output."""
    page = _page(db, tmp_path, "SM_NPQ_C01_001", folder, read_by=None)
    made = _import(client, page)
    line = _first_line(db, made["pass_id"])

    before = client.get(f"/api/segments/{line.id}/readings").json()["counting"]["transcription"]
    assert before["labelled_machine"] is True and before["basis"] == "newest-machine-unchosen"

    client.put(f"/api/segments/passes/{made['pass_id']}/ground-truth", json={"ground_truth": True})
    after = client.get(f"/api/segments/{line.id}/readings").json()["counting"]["transcription"]
    assert after["labelled_machine"] is False and after["basis"] == "newest-human"
    assert after["representation_id"] == before["representation_id"]
    # The page's working pass follows: a pass a person vouched for is a person's.
    passes = client.get(f"/api/segments/document/{page.id}").json()["passes"]
    assert next(p for p in passes if p["id"] == made["pass_id"])["working_basis"] == "human-touched"


def test_a_persons_corrections_inside_a_models_pass_count_and_only_they(client, db, tmp_path, folder):
    """#5499: "the bake-off counts person readings on any pass". A person correcting lines of a model's
    pass makes those lines ground truth; the model's other lines are not.
    WHY: the operator corrected three lines and the bake-off said "0 corrected lines"; scoring against the
    model's uncorrected lines, though, would score the model against itself."""
    page = _page(db, tmp_path, "SM_NPQ_C01_001", folder, read_by=None)
    made = _import(client, page)
    line = _first_line(db, made["pass_id"])
    imported = next(r for r in db.query(ContentRepresentation, segment_id=line.id) if r.kind == "transcription")
    corrected = client.post("/api/actions/invoke", json={"name": "representation.create", "params": {
        "document_id": page.id, "segment_id": line.id, "kind": "transcription",
        "content": "Corrected by a person", "corrects_representation_id": imported.id}})
    assert corrected.status_code == 200, corrected.text

    reference, why = evaluation.reference_page(db, page.id, None)
    assert why is None
    assert (reference["pass_id"], reference["trust"]) == (made["pass_id"], "person")
    assert [ln["text"] for ln in reference["lines"]] == ["Corrected by a person"]
    ready = _readiness(client)
    assert (ready["lines"], ready["pages"]) == (1, 1)
