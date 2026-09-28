"""QGIS `.points` files go in and out of a library with the CRS carried or declared, never assumed
(#5122, maps C4; `source.geo.gcp-tables`, `crs-explicit`, `crs-unknown`).

WHY: the QGIS georeferencer's GCP file is how most georeferencing is done and exchanged, and it is
the case the CRS rules exist for: a `.points` file with no `#CRS` line holds numbers in whatever
CRS the QGIS project had -- they look like degrees, and reading them as WGS 84 is exactly the guess
that puts a map in the wrong country. So they arrive HELD (`unknown`, the numbers as the file wrote
them) and are used only once a person declares the CRS; a file that names a projected CRS
(EPSG:3035) is held until PROJ ships. The pixel ends are QGIS's own convention (y negative
downwards) and the file has no image size, so the page's recorded size places them. If this
regresses, a map is placed from a CRS nobody stated, a pixel end is mirrored, or the file that goes
back to QGIS is not the one that came in.

Two real files from the Allmaps CLI's test inputs (MIT); what they say is read with the standard
library's csv, never with the engine's reader.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.api.routes.document.segment_readings import counting_by_kind, readings_of_segment
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, Segment, SegmentPass, Status
from tests.unit.api.test_page_text_follows_the_file import BOOT

FIXTURES = Path(__file__).parents[1] / "formats" / "fixtures"
NO_CRS = FIXTURES / "allmaps_qgis_no_crs.points"
LAEA = FIXTURES / "allmaps_qgis_laea_3035.points"
SIZE = (7000, 7000)   # the page's recorded size: the file states none


def _rows(path: Path) -> list[dict[str, str]]:
    lines = [line for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    return list(csv.DictReader(lines))


def _import(db, path: Path, size=SIZE) -> str:
    doc = Document(name="map.jpg", doc_type=DocType.file, file_type=FileType.image, path="/p/map.jpg",
                   status=Status.completed, metadata={"width": size[0], "height": size[1]} if size else {})
    db.save(doc)
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(path)}, BOOT)
    return doc.id


def _gcps(db, doc_id):
    return sorted((s for s in db.all(Segment) if s.document_id == doc_id and s.kind == "control-point"),
                  key=lambda s: (s.anchor.shapes[0].points[0][0], s.anchor.shapes[0].points[0][1]))


def _world(db, segment_id) -> dict:
    counted = counting_by_kind(db, segment_id, readings_of_segment(db, segment_id))["world-point"]
    return json.loads(db.get(ContentRepresentation, counted.representation_id).content)


def test_no_crs_stated_is_held_unconverted_with_its_pixels_placed(db, client):
    doc_id = _import(db, NO_CRS)
    gcps = _gcps(db, doc_id)
    rows = sorted(_rows(NO_CRS), key=lambda r: (float(r["sourceX"]), -float(r["sourceY"])))
    assert len(gcps) == len(rows) == 5
    for gcp, row in zip(gcps, rows):
        x, y = gcp.anchor.shapes[0].points[0]
        assert (round(x * SIZE[0], 6), round(y * SIZE[1], 6)) == (float(row["sourceX"]), -float(row["sourceY"]))
        world = _world(db, gcp.id)
        assert (world["crs"], world["lon"], world["lat"]) == ("unknown", None, None)
        assert world["as_entered"] == [float(row["mapX"]), float(row["mapY"])]
    [pass_id] = {g.pass_id for g in gcps}
    got = client.get(f"/api/georeference/passes/{pass_id}/transform").json()
    assert got["gcps"] == [] and len(got["not_used"]) == 5            # nothing placed on a guess


def test_a_projected_crs_is_named_and_held(db, client):
    doc_id = _import(db, LAEA)
    world = _world(db, _gcps(db, doc_id)[0].id)
    assert (world["crs_in"], world["crs"]) == ("EPSG:3035", "unknown") and "no conversion available" in world["conversion"]


def test_declared_wgs84_they_place_the_map_and_go_back_out_as_they_came(db, client):
    doc_id = _import(db, NO_CRS)
    for gcp in _gcps(db, doc_id):
        held = counting_by_kind(db, gcp.id, readings_of_segment(db, gcp.id))["world-point"].representation_id
        numbers = _world(db, gcp.id)["as_entered"]
        registry.invoke(db, "representation.create", {    # a person declares the CRS: a correction
            "document_id": doc_id, "segment_id": gcp.id, "kind": "world-point", "corrects_representation_id": held,
            "content": json.dumps({"coordinates": numbers, "crs": "EPSG:4326", "axis_order": "lon,lat"})}, BOOT)
    [pass_id] = {p.id for p in db.all(SegmentPass) if p.document_id == doc_id}
    assert len(client.get(f"/api/georeference/passes/{pass_id}/transform").json()["gcps"]) == 5

    response = client.get(f"/api/documents/{doc_id}/export/qgis-points")
    assert response.status_code == 200, response.text
    content = response.json()["content"]
    assert content.startswith('#CRS: GEOGCS["WGS 84"') and 'AUTHORITY["EPSG","4326"]]' in content.splitlines()[0]
    out = sorted((float(r["mapX"]), float(r["mapY"]), float(r["sourceX"]), float(r["sourceY"]))
                 for r in csv.DictReader(content.splitlines()[1:]))
    came = sorted((float(r["mapX"]), float(r["mapY"]), float(r["sourceX"]), float(r["sourceY"])) for r in _rows(NO_CRS))
    assert [tuple(round(v, 6) for v in row) for row in out] == [tuple(round(v, 6) for v in row) for row in came]


def test_a_page_with_no_recorded_size_is_refused_by_name(db, client):
    doc = Document(name="map.jpg", doc_type=DocType.file, file_type=FileType.image, path="/p/map.jpg",
                   status=Status.completed)
    db.save(doc)
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as refused:
        registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(NO_CRS)}, BOOT)
    assert refused.value.status_code == 422 and "no image size" in str(refused.value.detail)
    assert not [p for p in db.all(SegmentPass) if p.document_id == doc.id]
