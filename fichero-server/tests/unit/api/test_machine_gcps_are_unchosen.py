"""A machine's control points are shown LABELLED, unchosen, until a person chooses them; and a
georeferencing pass is never the page's text pass (#5122, maps C1; `source.geo.machine-gcps-unchosen`,
`source.geo.georef-is-a-pass`).

WHY: a georeference a machine proposed (junctions matched to a modern map) is a guess, and every
place worked out through it inherits the guess -- so the answer says so, the way a machine's
reading is labelled, until a person chooses the pass. And a georeferencing pass holds control
points, not text: ranked with the text passes, the imported georeference (the imported tier)
outranked the page's transcription and the page's text went BLANK; choosing one would also have
retired a person's choice of the text pass. So the two kinds are ranked, and chosen, apart. If this
regresses, a page's text disappears when its map is georeferenced, a machine's guess is shown as
the record, or choosing one pass silently undoes the other choice.

Real files: the Arabic PAGE page (its text) and the Allmaps Paris plan (its GCPs), through
format.import.
"""

from __future__ import annotations

import json

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.models import SegmentPass
from tests.unit.api.test_a_georeferencing_file_imports_as_a_pass import PARIS, _annotation, _file_gcps
from tests.unit.api.test_page_text_follows_the_file import BOOT
from tests.unit.api.test_reader_directions import ARABIC

MACHINE = ActionContext(actor="junction-matcher", run_id="run-1", is_bootstrap=True)
SOURCE = _annotation(PARIS)["target"]["source"]
W, H = SOURCE["width"], SOURCE["height"]


def _page_with_text(db) -> str:
    from fichero_server.models import DocType, Document, FileType, Status

    doc = Document(name="plan.jpg", doc_type=DocType.file, file_type=FileType.image, path="/p/plan.jpg",
                   status=Status.completed, metadata={"width": W, "height": H})
    db.save(doc)
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(ARABIC)}, BOOT)
    return doc.id


def _machine_georeference(db, doc_id: str) -> str:
    pass_id = registry.invoke(db, "segment.pass_create", {"document_id": doc_id, "name": "matched"}, MACHINE).result["id"]
    for (px, py), (lon, lat) in _file_gcps(PARIS):
        segment = registry.invoke(db, "segment.create", {
            "document_id": doc_id, "pass_id": pass_id, "kind": "control-point",
            "anchor": {"document_id": doc_id, "shapes": [{"kind": "point", "points": [[px / W, py / H]]}]},
        }, MACHINE).result["segment_ids"][0]
        registry.invoke(db, "representation.create", {
            "document_id": doc_id, "segment_id": segment, "kind": "world-point",
            "content": json.dumps({"coordinates": [lon, lat], "crs": "EPSG:4326", "axis_order": "lon,lat"})}, MACHINE)
    registry.invoke(db, "georef.set_transformation", {"pass_id": pass_id, "transformation": "polynomial-1"}, MACHINE)
    return pass_id


def test_a_georeference_imported_onto_a_page_leaves_its_text_alone(db, client):
    doc_id = _page_with_text(db)
    before = document_text(db, doc_id)
    registry.invoke(db, "format.import", {"document_id": doc_id, "path": str(PARIS)}, BOOT)
    after = document_text(db, doc_id)
    assert (after.pass_id, after.text) == (before.pass_id, before.text) and after.text


def test_a_machines_gcps_are_unchosen_until_a_person_chooses_them(db, client):
    doc_id = _page_with_text(db)
    text_pass = document_text(db, doc_id).pass_id
    registry.invoke(db, "pass.choose_working", {"document_id": doc_id, "pass_id": text_pass}, BOOT)
    machine = _machine_georeference(db, doc_id)

    got = client.get(f"/api/georeference/passes/{machine}/transform").json()
    assert (got["pass_provenance"], got["working"], got["unchosen"]) == ("workflow", True, True)

    registry.invoke(db, "pass.choose_working", {"document_id": doc_id, "pass_id": machine}, BOOT)
    got = client.get(f"/api/georeference/passes/{machine}/transform").json()
    assert (got["pass_basis"], got["unchosen"]) == ("chosen", False)
    text = document_text(db, doc_id)
    assert (text.pass_id, text.pass_basis) == (text_pass, "chosen")      # the text choice still stands


def test_with_two_georeferences_the_rule_picks_and_says_why(db, client):
    doc_id = _page_with_text(db)
    registry.invoke(db, "format.import", {"document_id": doc_id, "path": str(PARIS)}, BOOT)
    machine = _machine_georeference(db, doc_id)
    [imported] = [p.id for p in db.all(SegmentPass) if p.document_id == doc_id and p.transformation and p.id != machine]
    label = registry.invoke(db, "segment.pass_create", {"document_id": doc_id, "name": "names"}, BOOT).result["id"]
    place = registry.invoke(db, "segment.create", {
        "document_id": doc_id, "pass_id": label, "kind": "place",
        "anchor": {"document_id": doc_id, "shapes": [{"kind": "point", "points": [[0.4, 0.5]]}]}}, BOOT).result["segment_ids"][0]
    got = client.get(f"/api/georeference/segments/{place}/world-shape").json()
    # An import has no rank of its own (ruled 2026-10-04, #5443): the machine's georeference came
    # later, so by date it is the working one -- and, a machine's, it says it is unchosen.
    assert imported != machine
    assert (got["pass_id"], got["pass_basis"], got["unchosen"]) == (machine, "newest-machine-unchosen", True)
