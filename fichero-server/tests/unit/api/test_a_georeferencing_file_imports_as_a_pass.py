"""A georeferencing file imports as a pass: its GCPs with both ends, its mask, its
transformation (#5122; `source.geo.georef-is-a-pass`, `source.geo.mask`, `iiif-georef-in`).

WHY: a IIIF georeference file was refused on import because a library could not hold a GCP's
world end; keeping only the pixel end would have lost the half that makes it a control point.
Now each GCP is a point segment (the pixel end) with a `world-point` reading (the world end), the
mask is an area segment each GCP `controls`, and the pass says its transformation type as a typed
column. If this regresses, a map's georeferencing is refused again, or arrives with a place on
the earth missing, moved, or tied to the wrong mask.

The two files are the real Allmaps plans of Paris (published dialect) and Delft (earlier
dialect), MIT; what they say is read with the standard library's json, not the engine's reader.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.db import Database
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, Segment, SegmentPass, Status
from fichero_server.models.typed_links import TypedLink
from tests.unit.api.test_page_text_follows_the_file import BOOT

FIXTURES = Path(__file__).parents[1] / "formats" / "fixtures"
PARIS = FIXTURES / "allmaps_paris_thin_plate_spline.georef.json"
DELFT = FIXTURES / "allmaps_delft_earlier_dialect.georef.json"


def _annotation(path: Path) -> dict:
    data = json.loads(path.read_text())
    return data["items"][0] if data.get("type") == "AnnotationPage" else data


def _file_gcps(path: Path) -> list[tuple[list[float], list[float]]]:
    features = _annotation(path)["body"]["features"]
    return [(f["properties"].get("resourceCoords") or f["properties"]["pixelCoords"], f["geometry"]["coordinates"])
            for f in features]


def _import(db, path: Path, size: tuple[int, int]) -> str:
    doc = Document(name=path.stem, doc_type=DocType.file, file_type=FileType.image, path=f"/p/{path.stem}.jpg",
                   status=Status.completed, metadata={"width": size[0], "height": size[1]})
    db.save(doc)
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(path)}, BOOT)
    return doc.id


def assert_the_pass_matches_the_file(db, client, path: Path, size: tuple[int, int]) -> None:
    doc_id = _import(db, path, size)
    [pass_row] = [p for p in db.all(SegmentPass) if p.document_id == doc_id]
    assert pass_row.transformation == "thin-plate-spline"            # the file's `thinPlateSpline`
    listed = client.get(f"/api/segments/document/{doc_id}").json()
    assert [p["transformation"] for p in listed["passes"] if p["id"] == pass_row.id] == ["thin-plate-spline"]

    segments = [s for s in db.all(Segment) if s.pass_id == pass_row.id]
    gcps = [s for s in segments if s.kind == "control-point"]
    masks = [s for s in segments if s.kind == "mask"]
    worlds = {r.segment_id: json.loads(r.content) for r in db.all(ContentRepresentation)
              if r.kind == "world-point" and r.segment_id in {g.id for g in gcps}}
    got = sorted(
        ((round(g.anchor.shapes[0].points[0][0] * size[0], 3), round(g.anchor.shapes[0].points[0][1] * size[1], 3)),
         (worlds[g.id]["lon"], worlds[g.id]["lat"]))
        for g in gcps)
    expected = sorted(((float(px), float(py)), (lon, lat)) for (px, py), (lon, lat) in _file_gcps(path))
    assert got == expected                                           # both ends of every GCP, as the file says
    assert {w["crs"] for w in worlds.values()} == {"EPSG:4326"}
    assert len(masks) == 1 and masks[0].anchor.polygon
    links = [l for l in db.all(TypedLink) if l.link_type == "controls" and l.to_id == masks[0].id]
    assert sorted(l.from_id for l in links) == sorted(g.id for g in gcps)


def test_the_published_dialect_imports_with_both_ends_of_every_gcp(db, client):
    source = _annotation(PARIS)["target"]["source"]
    assert_the_pass_matches_the_file(db, client, PARIS, (source["width"], source["height"]))


def test_the_earlier_dialect_imports_too(db, client):
    import re

    svg = _annotation(DELFT)["target"]["selector"]["value"]
    width, height = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', svg).groups())
    assert_the_pass_matches_the_file(db, client, DELFT, (width, height))


def test_an_existing_library_gains_the_transformation_column_on_open(tmp_path):
    path = tmp_path / "old.duckdb"
    first = Database(path)
    first.close()
    conn = duckdb.connect(str(path))
    [table] = [r[0] for r in conn.execute(
        "SELECT table_name FROM information_schema.columns WHERE column_name = 'transformation'").fetchall()]
    # A library from before #5122: the same table without the column (rebuilt, because indexes
    # depend on the table and DuckDB will not drop a column under them).
    columns = [r[0] for r in conn.execute(
        f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' "
        "AND column_name <> 'transformation' ORDER BY ordinal_position").fetchall()]
    conn.execute(f"CREATE TABLE old_passes AS SELECT {', '.join(columns)} FROM {table}")
    conn.execute(f"DROP TABLE {table}")
    conn.execute(f"ALTER TABLE old_passes RENAME TO {table}")
    conn.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (id)")
    assert "transformation" not in {r[0] for r in conn.execute(
        f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'").fetchall()}
    conn.close()
    reopened = Database(path)
    try:
        reopened.save(SegmentPass(document_id="d", name="georeference", provenance_kind="human",
                                  transformation="polynomial-1"))
        assert [p.transformation for p in reopened.all(SegmentPass)] == ["polynomial-1"]
    finally:
        reopened.close()
