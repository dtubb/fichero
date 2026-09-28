"""Every coordinate the library already holds says it is WGS 84; one in another CRS is refused
(maps D5, #4933; `source.geo.crs-declared-on-existing`).

WHY: a claim's point (`GeoPoint`) and a place's evidence (`EvidentialPlace`) held a latitude and a
longitude and nothing saying in what -- the one record kind in the library where "these two numbers
are degrees on WGS 84" was an assumption rather than a statement. Every world point written since
maps A says its CRS; these did not. The change is ADDITIVE: no row is rewritten, because every
number they ever held came from a geocoder or the map, both WGS 84 -- so an older row reads back
declaring it, and a write that names any other CRS is refused rather than stored as if it were
degrees. If this regresses, a projected coordinate (metres) lands in a lat/lon field and the pin
goes somewhere in the ocean, or an older library's points stop saying what they are.

The older row is made the way an older build left it: the JSON written straight into the file
after close, with no `crs` key, then opened by this build.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from fichero_server.db import Database
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import (
    EvidenceBasis, EvidentialPlace, GeoPoint, KnowledgeClaim, PlaceGeometryType,
)

POPAYAN = {"lat": 2.4448, "lon": -76.6147, "place_name": "Popayán"}


def test_a_claim_an_older_build_wrote_reads_back_as_wgs84(tmp_path: Path):
    path = tmp_path / "old.duckdb"
    first = Database(path)
    doc = Document(name="page.txt", doc_type=DocType.page)
    first.save(doc)
    claim = KnowledgeClaim(text="Pedro travelled to Popayán.", source_document_id=doc.id,
                           claim_geo=GeoPoint(**POPAYAN),
                           place_values=[EvidentialPlace(label="Popayán", geometry_type=PlaceGeometryType.point,
                                                         lat=2.4448, lon=-76.6147, basis=EvidenceBasis.inferred)])
    first.save(claim)
    table = first._table_name(KnowledgeClaim)
    first.close()
    conn = duckdb.connect(str(path))
    geo_col, places_col = conn.execute(f"SELECT claim_geo, place_values FROM {table} WHERE id = ?", [claim.id]).fetchone()
    older_geo = {k: v for k, v in json.loads(geo_col).items() if k != "crs"}
    older_places = [{k: v for k, v in place.items() if k != "crs"} for place in json.loads(places_col)]
    assert "crs" not in older_geo and all("crs" not in p for p in older_places)
    conn.execute(f"UPDATE {table} SET claim_geo = ?, place_values = ? WHERE id = ?",
                 [json.dumps(older_geo), json.dumps(older_places), claim.id])
    conn.close()

    back = Database(path).get(KnowledgeClaim, claim.id)
    assert back.claim_geo.crs == "EPSG:4326"
    assert (back.claim_geo.lat, back.claim_geo.lon) == (2.4448, -76.6147)      # no number touched
    assert [p.crs for p in back.place_values] == ["EPSG:4326"]


def test_the_claim_route_says_the_crs_and_refuses_another(client, db):
    doc = Document(name="Source Doc", doc_type=DocType.file)
    db.save(doc)
    made = client.post("/api/claims", json={"text": "Pedro left for Popayán.", "source_document_id": doc.id,
                                             "claim_geo": POPAYAN})
    assert made.status_code == 200, made.text
    assert made.json()["claim_geo"]["crs"] == "EPSG:4326"
    assert client.get(f"/api/claims/{made.json()['id']}").json()["claim_geo"]["crs"] == "EPSG:4326"
    # Web Mercator metres in the lat/lon fields would be refused by range anyway; a CRS named
    # outright must be refused by NAME, whatever the numbers -- nothing is converted here.
    refused = client.post("/api/claims", json={"text": "Elsewhere.", "source_document_id": doc.id,
                                                "claim_geo": {**POPAYAN, "crs": "EPSG:3857"}})
    assert refused.status_code == 422, refused.text


def test_the_geocoder_writes_wgs84_and_says_so():
    from fichero_server.media import geo

    point, source = geo.geocode_with_source("Popayán", online=False)
    assert source == geo.SOURCE_GAZETTEER and point.crs == "EPSG:4326"
    assert point.model_dump()["crs"] == "EPSG:4326"
