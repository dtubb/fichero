"""A georeferencing pass exports from the library as a georef/1 annotation that passes the
checker, with the same GCPs, mask and transformation the file came in with, and what changed
since (#5122, maps C3; `source.geo.iiif-georef-out`, `iiif-georef-round-trip` through a library).

WHY: the format wrote and checked georef/1 from a file's own reading, but a library had nothing to
give it: an export of the page wrote the text pass, and a pass's GCPs had no world end on the way
out. Now the export of `iiif-georef` defaults to the image's working georeferencing pass and writes
each GCP's pixel end and counted world end, the mask each controls, and the pass's transformation
-- so a correction made in the library is in the file sent to Allmaps. If this regresses, the
export is empty, loses GCPs, or sends a place that was corrected as it was before.

The file is the real Allmaps Paris plan (MIT); in and out are compared with the standard library's
json, not the engine's reader.
"""

from __future__ import annotations

import json

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.api.routes.document.segment_readings import counting_by_kind, readings_of_segment
from fichero_server.models import Segment
from tests.unit.api.test_a_georeferencing_file_imports_as_a_pass import PARIS, _annotation, _file_gcps, _import
from tests.unit.api.test_page_text_follows_the_file import BOOT

SOURCE = _annotation(PARIS)["target"]["source"]
W, H = SOURCE["width"], SOURCE["height"]


def _export(client, doc_id: str) -> tuple[dict, dict]:
    response = client.get(f"/api/documents/{doc_id}/export/iiif-georef")
    assert response.status_code == 200, response.text
    body = response.json()
    return json.loads(body["content"]), body


def _gcps(annotation: dict) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return sorted((tuple(round(v, 3) for v in f["properties"]["resourceCoords"]), tuple(f["geometry"]["coordinates"]))
                  for f in annotation["body"]["features"])


def test_the_pass_goes_out_as_it_came_in(db, client):
    doc_id = _import(db, PARIS, (W, H))
    out, body = _export(client, doc_id)
    assert body["filename"].endswith(".georef.json")
    assert _gcps(out) == sorted((tuple(float(v) for v in px), tuple(w)) for px, w in _file_gcps(PARIS))
    assert out["body"]["transformation"] == {"type": "thinPlateSpline"}
    assert out["motivation"] == "georeferencing" and "SvgSelector" == out["target"]["selector"]["type"]


def test_a_correction_in_the_library_is_in_the_file(db, client):
    doc_id = _import(db, PARIS, (W, H))
    gcp = sorted((s for s in db.all(Segment) if s.document_id == doc_id and s.kind == "control-point"), key=lambda s: s.id)[0]
    old = counting_by_kind(db, gcp.id, readings_of_segment(db, gcp.id))["world-point"].representation_id
    registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": gcp.id, "kind": "world-point", "corrects_representation_id": old,
        "content": json.dumps({"coordinates": [2.3, 48.86], "crs": "EPSG:4326", "axis_order": "lon,lat"})}, BOOT)
    registry.invoke(db, "georef.set_transformation", {"pass_id": gcp.pass_id, "transformation": "polynomial-1"}, BOOT)
    out, _body = _export(client, doc_id)
    assert (2.3, 48.86) in [w for _px, w in _gcps(out)]
    assert out["body"]["transformation"] == {"type": "polynomial", "options": {"order": 1}}
