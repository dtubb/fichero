"""A georeferenced map says what date it DEPICTS, apart from when it was made; a boundary drawn on
it becomes one of a place's geometries, remembering the segment, pass and map it came from, and
dated by what the map depicts (maps D8, #5120; `source.geo.map-depicts-date`,
`source.geo.boundary-from-map`).

WHY: a map is evidence about a place at the time it shows, which is often not when it was printed --
a 1900 atlas plate of Roman Lutetia shows c. 300. A geometry adopted from a map with the print date,
or with no date, puts the Roman walls on the 1900 city; one that forgets which segment and pass
it came from cannot be re-worked when a control point is corrected or checked against the sheet.
And a boundary drawn outside the map (the margin, the cartouche) is refused, never extrapolated
onto the earth. If this regresses, an as-of-date query answers with a shape from the wrong century,
or a boundary cannot be traced back to the map.

The map is the real Allmaps Paris plan (MIT annotation) through format.import: the Internet
Archive's "Plan général de l'Exposition universelle de 1889" (its catalogue record vendored, read
with json). The boundary is what a person draws on it: a ring among the file's own control points.
"""

from __future__ import annotations

import json
from pathlib import Path

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import SegmentPass
from fichero_server.models.knowledge import EntityType, KnowledgeEntity
from tests.unit.api.test_a_segments_place_in_the_world import _segment, _setup

MAP = json.loads((Path(__file__).resolve().parent / "fixtures" / "maps" / "ia_plangeneraldelex00unse_metadata.json").read_text())
#: What the plan depicts: the 1889 exhibition, open 6 May to 31 October 1889 -- its subject, not its print date.
EXHIBITION = {"start": "1889-05-06", "end": "1889-10-31", "label": "Exposition universelle de 1889",
              "basis": "source_anchored", "source_excerpt": MAP["subject"][0]}
RING = [[0.3, 0.3], [0.5, 0.3], [0.5, 0.6], [0.3, 0.6]]


def _invoke(client, name, params, expect=200):
    response = client.post("/api/actions/invoke", json={"name": name, "params": params})
    assert response.status_code == expect, response.text
    return response.json()


def _georef_pass(db, doc_id):
    return next(p for p in db.all(SegmentPass) if p.document_id == doc_id and p.transformation and p.deleted_at is None)


def test_the_map_says_what_it_depicts_apart_from_when_it_was_made(db, client):
    doc_id, labels = _setup(db)
    georef = _georef_pass(db, doc_id)
    made = _invoke(client, "georef.set_depicts", {"pass_id": georef.id, "depicts": EXHIBITION})
    assert made["result"]["depicts"]["start"] == "1889-05-06"
    boundary = _segment(db, doc_id, labels, {"kind": "polygon", "points": RING})
    shape = client.get(f"/api/georeference/segments/{boundary}/world-shape").json()
    assert shape["depicts"]["label"] == "Exposition universelle de 1889"
    assert MAP["date"] == "1889"             # made: the catalogue's date, kept on the document, not here
    undone = client.post(f"/api/actions/audit/{made['audit_id']}/undo")
    assert undone.status_code == 200 and db.get(SegmentPass, georef.id).depicts is None


def test_a_boundary_drawn_on_the_map_becomes_the_places_dated_geometry(db, client):
    doc_id, labels = _setup(db)
    georef = _georef_pass(db, doc_id)
    _invoke(client, "georef.set_depicts", {"pass_id": georef.id, "depicts": EXHIBITION})
    grounds = KnowledgeEntity(canonical_name="Exposition universelle de 1889 grounds", entity_type=EntityType.location)
    db.save(grounds)
    boundary = _segment(db, doc_id, labels, {"kind": "polygon", "points": RING})
    shape = client.get(f"/api/georeference/segments/{boundary}/world-shape").json()
    adopted = _invoke(client, "entity.adopt_boundary", {"entity_id": grounds.id, "segment_id": boundary})
    [place] = db.get(KnowledgeEntity, grounds.id).place_values
    assert place.geojson == shape["geometry"] and place.geometry_type.value == "region"
    assert (place.adopted_from_segment_id, place.adopted_from_pass_id, place.source_document_id) == (boundary, georef.id, doc_id)
    assert place.precision_m == shape["error_m"] and place.basis.value == "source_anchored"
    assert (place.when.start, place.when.end) == ("1889-05-06", "1889-10-31") and adopted["result"]["dated"] is True
    # As of a date: there in 1889, not before or after -- the map's date, not the print's nor today's.
    assert client.get(f"/api/entities/{grounds.id}/place", params={"as_of": "1889-07-14"}).json()["geometries"]
    assert client.get(f"/api/entities/{grounds.id}/place", params={"as_of": "1900"}).json()["reason"] == "none valid in 1900"
    undone = client.post(f"/api/actions/audit/{adopted['audit_id']}/undo")
    assert undone.status_code == 200 and db.get(KnowledgeEntity, grounds.id).place_values == []


def test_a_map_nobody_has_dated_gives_an_undated_geometry(db, client):
    doc_id, labels = _setup(db)
    paris = KnowledgeEntity(canonical_name="Paris", entity_type=EntityType.location)
    db.save(paris)
    boundary = _segment(db, doc_id, labels, {"kind": "polygon", "points": RING})
    adopted = _invoke(client, "entity.adopt_boundary", {"entity_id": paris.id, "segment_id": boundary})
    assert adopted["result"]["dated"] is False
    answer = client.get(f"/api/entities/{paris.id}/place", params={"as_of": "1889"}).json()
    assert answer["geometries"] == [] and len(answer["undated"]) == 1      # listed, never counted as valid


def test_a_boundary_outside_the_map_is_refused(db, client):
    doc_id, labels = _setup(db)
    paris = KnowledgeEntity(canonical_name="Paris", entity_type=EntityType.location)
    db.save(paris)
    margin = _segment(db, doc_id, labels, {"kind": "polygon", "points": [[0.001, 0.001], [0.01, 0.001], [0.01, 0.01]]})
    _invoke(client, "entity.adopt_boundary", {"entity_id": paris.id, "segment_id": margin}, expect=422)
    assert db.get(KnowledgeEntity, paris.id).place_values == []


def test_a_library_from_before_the_column_opens_and_gains_it(tmp_path):
    """`depicts` is a new typed column on the pass: a library written before it opens (the reconcile
    adds the column), its passes read back undated, and a date can then be set."""
    import duckdb

    from fichero_server.db import Database
    from fichero_server.models.knowledge import ProvenanceKind

    path = tmp_path / "older.duckdb"
    first = Database(path)
    row = SegmentPass(document_id="d", name="georef", provenance_kind=ProvenanceKind.human, transformation="helmert")
    first.save(row)
    table = first._table_name(SegmentPass)
    first.close()
    conn = duckdb.connect(str(path))
    # The file as an older build left it: no `depicts` column (its indexes go first -- DuckDB will not
    # alter a table something depends on -- and the open below recreates them).
    for (index,) in conn.execute("SELECT index_name FROM duckdb_indexes() WHERE table_name = ?", [table]).fetchall():
        conn.execute(f'DROP INDEX "{index}"')
    conn.execute(f"ALTER TABLE {table} DROP COLUMN depicts")
    assert "depicts" not in {c[0] for c in conn.execute(f"DESCRIBE {table}").fetchall()}
    conn.close()
    second = Database(path)
    back = second.get(SegmentPass, row.id)
    assert back.depicts is None and back.transformation == "helmert"
    from fichero_server.models.knowledge import EvidentialDateRange

    back.depicts = EvidentialDateRange(start="1889", end="1889", basis="asserted")
    second.save(back)
    assert second.get(SegmentPass, row.id).depicts.start == "1889"



def test_a_place_stored_under_the_first_names_reads_back_under_the_new_ones(tmp_path):
    """D8 first stored the segment and pass as `source_segment_id` / `source_pass_id`; the first is
    the claims' legacy ARTIFACT-entry field's name, so it was renamed (a Segment record id must not
    share it). A place written under the old names -- the file as that build left it -- reads back
    under the new ones, the values intact."""
    import duckdb

    from fichero_server.db import Database
    from fichero_server.models.knowledge import EvidentialPlace

    path = tmp_path / "d8.duckdb"
    first = Database(path)
    entity = KnowledgeEntity(canonical_name="grounds", entity_type=EntityType.location,
                             place_values=[EvidentialPlace(label="grounds", basis="source_anchored",
                                                           adopted_from_segment_id="seg-1", adopted_from_pass_id="pass-1")])
    first.save(entity)
    table = first._table_name(KnowledgeEntity)
    first.close()
    conn = duckdb.connect(str(path))
    [raw] = json.loads(conn.execute(f"SELECT place_values FROM {table} WHERE id = ?", [entity.id]).fetchone()[0])
    raw["source_segment_id"], raw["source_pass_id"] = raw.pop("adopted_from_segment_id"), raw.pop("adopted_from_pass_id")
    conn.execute(f"UPDATE {table} SET place_values = ? WHERE id = ?", [json.dumps([raw]), entity.id])
    conn.close()
    [place] = Database(path).get(KnowledgeEntity, entity.id).place_values
    assert (place.adopted_from_segment_id, place.adopted_from_pass_id) == ("seg-1", "pass-1")
    assert "source_segment_id" not in place.model_dump()
