"""One ground control point is corrected alone: moved, retyped or withdrawn, as ONE audited,
undoable action that changes that GCP and no other (#5122; `source.geo.gcp-corrected-alone`).

WHY: the way a person finds and fixes a bad georeferencing is one point at a time -- the one GCP
typed wrong, the one on the wrong road junction. If fixing it rewrote the pass (or re-imported
the file), every other point's history and maker would go with it, and the transform would
shift under points nobody touched. Each correction is the ordinary segment or reading action:
move = `segment.update`, retype = a `world-point` reading that CORRECTS the old one (#5175: it
counts), withdraw = `segment.delete`; each undoes through the audit trail. If this regresses, one
fix touches the others, or cannot be undone.

The pass is the real Allmaps Paris plan (MIT) through format.import.
"""

from __future__ import annotations

import json

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.api.routes.document.segment_readings import counting_by_kind, readings_of_segment
from fichero_server.models import ContentRepresentation, Segment
from fichero_server.models.anchors import SourceAnchor
from tests.unit.api.test_a_georeferencing_file_imports_as_a_pass import PARIS, _annotation, _import
from tests.unit.api.test_page_text_follows_the_file import BOOT


def _pass(db):
    source = _annotation(PARIS)["target"]["source"]
    doc_id = _import(db, PARIS, (source["width"], source["height"]))
    gcps = sorted((s for s in db.all(Segment) if s.document_id == doc_id and s.kind == "control-point"), key=lambda s: s.id)
    return doc_id, gcps


def _world(db, segment_id: str) -> dict:
    items = readings_of_segment(db, segment_id)
    counted = counting_by_kind(db, segment_id, items)["world-point"].representation_id
    return json.loads(next(r.content for r in db.all(ContentRepresentation) if r.id == counted))


def _state(db, gcps) -> dict:
    """Everything a correction could disturb, per GCP: its live row, its shape, its counted world end."""
    out = {}
    for g in gcps:
        row = db.get(Segment, g.id)
        out[g.id] = (row.deleted_at is None, row.anchor.model_dump_json(), json.dumps(_world(db, g.id), sort_keys=True))
    return out


def _only_one_changed(before: dict, after: dict, target: str) -> None:
    assert after[target] != before[target]
    assert {k: v for k, v in after.items() if k != target} == {k: v for k, v in before.items() if k != target}


def test_moving_one_gcp_moves_it_alone_and_undoes(db, client):
    _doc, gcps = _pass(db)
    target = gcps[1]
    before = _state(db, gcps)
    moved = SourceAnchor(document_id=target.document_id, shapes=[{"kind": "point", "points": [[0.5, 0.5]]}])
    result = registry.invoke(db, "segment.update", {"segment_id": target.id, "expected_version": target.version,
                                                   "anchor": moved.model_dump(mode="json")}, BOOT)
    _only_one_changed(before, _state(db, gcps), target.id)
    assert client.post(f"/api/actions/audit/{result.audit_id}/undo").status_code == 200
    assert _state(db, gcps) == before


def test_retyping_one_gcps_place_is_a_correction_that_counts_and_undoes(db, client):
    doc_id, gcps = _pass(db)
    target = gcps[2]
    before = _state(db, gcps)
    old = counting_by_kind(db, target.id, readings_of_segment(db, target.id))["world-point"].representation_id
    result = registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": target.id, "kind": "world-point",
        "content": json.dumps({"coordinates": [2.2950, 48.8580], "crs": "EPSG:4326", "axis_order": "lon,lat"}),
        "corrects_representation_id": old}, BOOT)
    assert (_world(db, target.id)["lon"], _world(db, target.id)["lat"]) == (2.2950, 48.8580)
    _only_one_changed(before, _state(db, gcps), target.id)
    assert client.post(f"/api/actions/audit/{result.audit_id}/undo").status_code == 200
    assert _state(db, gcps) == before


def test_withdrawing_one_gcp_withdraws_it_alone_and_undoes(db, client):
    _doc, gcps = _pass(db)
    target = gcps[0]
    before = _state(db, gcps)
    result = registry.invoke(db, "segment.delete", {"segment_ids": [target.id],
                                                   "expected_versions": {target.id: target.version}}, BOOT)
    after = _state(db, gcps)
    assert after[target.id][0] is False
    _only_one_changed(before, after, target.id)
    assert client.post(f"/api/actions/audit/{result.audit_id}/undo").status_code == 200
    assert _state(db, gcps) == before
