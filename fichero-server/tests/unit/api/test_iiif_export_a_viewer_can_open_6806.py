"""A local page's IIIF export names itself by the address it is served at, carries every line with its own
maker and outline (#6806: `iiif.export.ids-are-absolute-and-resolve`, `iiif.export.every-line-with-its-outline`,
`iiif.export.maker-is-the-readings`).

WHY: measured 2026-11-20 and 2026-11-21: every id was a bare path, the manifest named itself
`/api/iiif/iiif/{id}/manifest` while it is served at `/api/iiif/iiif/manifest/{id}` (its own id answered 404), a
line with no reading was left out (5 annotations for 33 lines), every target was a box, and every annotation's
`creator` was the pass's maker, so lines a person typed said the segmenter made them. The page is the record-export
page (three lines imported from PAGE XML, a real image): line 1 a person's reading with a five-point outline,
line 2 a machine's reading, line 3 with its reading withdrawn. Tested through the routes, as a viewer reaches them.
"""
from __future__ import annotations

import datetime

import pytest

from fichero_server.api.routes.document.segment_readings import readings_of_segment
from fichero_server.models import ContentRepresentation, Segment
from fichero_server.models.knowledge import ProvenanceKind
from tests.unit.core.test_export_reads_the_record import LINES, library  # noqa: F401  (fixture)

pytestmark = pytest.mark.source_model

ORIGIN = "http://testserver"
OUTLINE = [[0.05, 0.10], [0.95, 0.10], [0.97, 0.20], [0.50, 0.26], [0.05, 0.20]]


def _ids(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "id" and isinstance(value, str):
                yield value
            yield from _ids(value)
    elif isinstance(node, list):
        for value in node:
            yield from _ids(value)


@pytest.fixture
def doc_id(db, library):  # noqa: F811
    first, second, third = library["lines"]
    row = db.get(Segment, first.segment_id)
    row.anchor = row.anchor.model_copy(update={"polygon": OUTLINE})
    db.save(row)
    for span, edit in ((first, {"provenance_kind": ProvenanceKind.human, "created_by": "historian"}),
                       (second, {"provenance_kind": ProvenanceKind.workflow, "producer_model": "vision-model"}),
                       (third, {"retracted_at": datetime.datetime.now(datetime.timezone.utc)})):
        (reading,) = [r for r in readings_of_segment(db, span.segment_id) if r.kind == "transcription"]
        stored = db.get(ContentRepresentation, reading.id)
        for name, value in edit.items():
            setattr(stored, name, value)
        db.save(stored)
    return library["doc"].id


def _manifest(client, doc_id):
    return client.get(f"/api/iiif/iiif/manifest/{doc_id}").json()


def test_every_id_is_absolute_and_the_manifest_is_served_at_its_own_id(client, doc_id):
    manifest = _manifest(client, doc_id)
    assert manifest["id"] == f"{ORIGIN}/api/iiif/iiif/manifest/{doc_id}"
    assert client.get(manifest["id"]).json() == manifest
    ids = list(_ids(manifest))
    assert ids and all(i.startswith(ORIGIN + "/") for i in ids), ids
    lines_page = client.get(manifest["items"][0]["annotations"][0]["id"])
    assert lines_page.status_code == 200
    assert all(i.startswith(ORIGIN + "/") for i in _ids(lines_page.json()))
    service = manifest["items"][0]["items"][0]["items"][0]["body"]["service"][0]["id"]
    assert client.get(f"{service}/info.json").status_code == 200


def test_every_line_is_written_with_its_outline_and_a_body_only_when_it_has_a_reading(client, doc_id):
    manifest = _manifest(client, doc_id)
    page = client.get(manifest["items"][0]["annotations"][0]["id"]).json()
    first, second, third = page["items"]
    assert [a.get("body", {}).get("value") for a in (first, second)] == [LINES[0], LINES[1]]
    assert "body" not in third
    # 600x240 canvas pixels: the five-point outline, not its box.
    assert first["target"]["source"].endswith("/canvas/1")
    selector = first["target"]["selector"]
    assert selector["type"] == "SvgSelector"
    assert 'points="30,24 570,24 582,48 300,62 30,48"' in selector["value"]
    assert first["baseline"] == [[20, 52], [580, 52]]


def test_each_annotation_names_who_made_that_reading(client, doc_id):
    page = client.get(_manifest(client, doc_id)["items"][0]["annotations"][0]["id"]).json()
    first, second, third = page["items"]
    assert first["creator"] == {"type": "Person", "name": "historian"}
    assert second["creator"] == {"type": "Software", "name": "vision-model"}
    assert "creator" not in third
