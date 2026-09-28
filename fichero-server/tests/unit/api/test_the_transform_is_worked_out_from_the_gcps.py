"""A georeferencing pass's transform is WORKED OUT from its GCPs and transformation type, with
every GCP's residual; the type is chosen by one undoable action that refuses too few GCPs (#5122;
`source.geo.transform-is-derived`, `residuals`, `transformation-type`).

WHY: the residual is how a person finds the one GCP typed wrong -- the one on the wrong junction
misses the fitted transform by hundreds of metres while the rest agree. A stored transform would
go stale the moment a GCP is corrected, so it is never stored: every read works it out, and says
which GCP set it came from (`gcp_set_version`) so a cache can tell. A type needing more GCPs than
the pass has cannot be fitted, and is refused saying how many it needs rather than producing a
transform that is not one. If this regresses, a wrong GCP hides, a corrected one is ignored, or
an unfittable transformation is accepted.

The pass is the real Allmaps Paris plan (MIT) through format.import; the checks are properties of
the fit (a thin-plate spline is exact at its GCPs; the moved GCP is the worst), not numbers
copied from the implementation.
"""

from __future__ import annotations

import json

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.api.routes.document.segment_readings import counting_by_kind, readings_of_segment
from fichero_server.models import Segment, SegmentPass
from tests.unit.api.test_a_georeferencing_file_imports_as_a_pass import PARIS, _annotation, _file_gcps, _import
from tests.unit.api.test_page_text_follows_the_file import BOOT


def _pass(db):
    source = _annotation(PARIS)["target"]["source"]
    doc_id = _import(db, PARIS, (source["width"], source["height"]))
    [pass_row] = [p for p in db.all(SegmentPass) if p.document_id == doc_id]
    return doc_id, pass_row.id


def _transform(client, pass_id: str) -> dict:
    response = client.get(f"/api/georeference/passes/{pass_id}/transform")
    assert response.status_code == 200, response.text
    return response.json()


def test_the_files_thin_plate_spline_is_exact_at_its_gcps(db, client):
    _doc, pass_id = _pass(db)
    got = _transform(client, pass_id)
    assert got["transformation"] == "thin-plate-spline"
    assert len(got["gcps"]) == len(_file_gcps(PARIS))
    assert all(g["residual_m"] < 0.01 and g["residual_px"] < 0.01 for g in got["gcps"])


def test_affine_misses_by_a_little_and_a_gcp_typed_wrong_misses_by_most(db, client):
    """Affine on this real plan misses by metres. Then one GCP is retyped 0.01 deg (~700 m) off,
    under HELMERT: four points against four parameters leaves the fit enough to single the bad one
    out whichever it is (checked for each of the four); under affine, four points leave one spare
    observation per axis, and least squares can spread one bad point's error so that another shows
    the largest residual -- a property of the method, which is why the check is made where the
    method can make it. The GCP is chosen by the FILE's order, never by a random id."""
    doc_id, pass_id = _pass(db)
    assert client.put(f"/api/georeference/passes/{pass_id}/transformation",
                      json={"transformation": "polynomial-1"}).status_code == 200
    affine = _transform(client, pass_id)
    assert 0 < affine["rms_m"] < 50                       # a real plan: a few metres off, not zero

    assert client.put(f"/api/georeference/passes/{pass_id}/transformation",
                      json={"transformation": "helmert"}).status_code == 200
    honest = _transform(client, pass_id)
    (px, py), _world = _file_gcps(PARIS)[1]
    source = _annotation(PARIS)["target"]["source"]
    wrong = next(g["segment_id"] for g in honest["gcps"]
                 if abs(g["pixel"][0] - px) < 0.01 and abs(g["pixel"][1] - py) < 0.01)
    old = counting_by_kind(db, wrong, readings_of_segment(db, wrong))["world-point"].representation_id
    lon, lat = next(g["world"] for g in honest["gcps"] if g["segment_id"] == wrong)
    registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": wrong, "kind": "world-point", "corrects_representation_id": old,
        "content": json.dumps({"coordinates": [lon + 0.01, lat], "crs": "EPSG:4326", "axis_order": "lon,lat"})}, BOOT)
    after = _transform(client, pass_id)
    assert after["gcp_set_version"] != honest["gcp_set_version"]          # a corrected GCP is a new set
    worst = max(after["gcps"], key=lambda g: g["residual_m"])
    assert worst["segment_id"] == wrong and worst["residual_m"] > 10 * honest["rms_m"]
    assert source["width"] > px                                           # the pixel is the file's own


def test_too_few_gcps_is_refused_with_the_number_needed_and_the_choice_undoes(db, client):
    _doc, pass_id = _pass(db)
    refused = client.put(f"/api/georeference/passes/{pass_id}/transformation", json={"transformation": "polynomial-2"})
    assert refused.status_code == 422 and "at least 6" in refused.text and "has 4" in refused.text
    assert client.put(f"/api/georeference/passes/{pass_id}/transformation",
                      json={"transformation": "unheard-of"}).status_code == 422
    chosen = client.put(f"/api/georeference/passes/{pass_id}/transformation", json={"transformation": "helmert"}).json()
    assert _transform(client, pass_id)["transformation"] == "helmert"
    assert client.post(f"/api/actions/audit/{chosen['audit_id']}/undo").status_code == 200
    assert _transform(client, pass_id)["transformation"] == "thin-plate-spline"
