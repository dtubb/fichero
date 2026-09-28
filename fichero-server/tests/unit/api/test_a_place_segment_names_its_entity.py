"""A segment that names a place is joined to the place ENTITY by a typed `names` link, with a maker
and a certainty (maps D, #5123; `source.geo.place-segment-names-entity`).

WHY: the gazetteer identity lives on the place entity, ruled 2026-09-27 -- ten letters that name
Popayán are ten `names` links to ONE entity, reconciled once. So a segment has to be able to reach
an entity: before this a typed link's end could be a segment, note, document, claim or canvas item,
never a knowledge-graph entity, and any unknown end kind was stored as given. If this regresses,
place names on a page cannot be tied to the place, or a link to a merged (gone) entity is made
quietly.

The line is the real Vienna Syriac folio's l_77, "in the land of Palestine" (read with lxml).
"""

from __future__ import annotations

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import Segment
from fichero_server.models.knowledge import EntityType, KnowledgeEntity
from tests.unit.api.test_reader_directions import SYRIAC, _import

PALESTINE = "ܦܠܣܛܝܢܐ"


def _line_77(db, client):
    root = etree.parse(str(SYRIAC)).getroot()
    l77 = next(el for el in root.iter("{*}TextLine") if el.get("id") == "l_77")
    assert PALESTINE in "".join(l77.find("{*}TextEquiv/{*}Unicode").itertext())
    doc_id = _import(db, SYRIAC)
    return next(s for s in db.all(Segment) if s.document_id == doc_id and s.metadata.get("source_id") == "l_77")


def _place(db, **fields) -> KnowledgeEntity:
    entity = KnowledgeEntity(canonical_name="Palestine", entity_type=EntityType.location, **fields)
    db.save(entity)
    return entity


def test_the_line_names_its_place_and_both_ends_see_it(db, client):
    line = _line_77(db, client)
    place = _place(db)
    made = client.post("/api/links", json={"from_id": line.id, "to_id": place.id, "link_type": "names",
                                           "to_kind": "entity", "certainty": 0.9})
    assert made.status_code == 200, made.text
    [from_place] = client.get(f"/api/links/of/{place.id}").json()["links"]
    assert (from_place["link_type"], from_place["other_kind"], from_place["other_id"]) == ("names", "segment", line.id)
    [from_line] = client.get(f"/api/links/of/{line.id}").json()["links"]
    assert (from_line["other_kind"], from_line["other_id"]) == ("entity", place.id)


def test_a_link_to_no_entity_or_a_merged_one_is_refused(db, client):
    line = _line_77(db, client)
    survivor = _place(db)
    merged = _place(db, merged_into_id=survivor.id)
    assert client.post("/api/links", json={"from_id": line.id, "to_id": "no-such-entity", "link_type": "names",
                                           "to_kind": "entity"}).status_code == 404
    refused = client.post("/api/links", json={"from_id": line.id, "to_id": merged.id, "link_type": "names",
                                              "to_kind": "entity"})
    assert refused.status_code == 422 and survivor.id in refused.text


def test_an_end_of_no_known_kind_is_refused(db, client):
    line = _line_77(db, client)
    refused = client.post("/api/links", json={"from_id": line.id, "to_id": "x", "link_type": "names", "to_kind": "gadget"})
    assert refused.status_code == 422 and "unknown link end kind" in refused.text
