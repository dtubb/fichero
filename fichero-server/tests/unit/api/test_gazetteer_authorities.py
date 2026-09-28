"""The gazetteers are authorities beside Wikidata, each identifier has ONE canonical URI, and one
that does not fit its authority is refused (maps D2, #5123; `source.geo.gazetteer-authorities`).

WHY: a place entity's identity is the gazetteer's (ruled 2026-09-27), and an identity is only
useful if it has one spelling -- "579885", "https://pleiades.stoa.org/places/579885/" and a typo
must not be three identities, or "every segment that names this Pleiades place" finds some and
misses the rest. So each authority states its URI form and its identifier's pattern; an identifier
given as its URI is read back to the id; anything else -- free text, a Wikidata number without
its Q -- is refused, never stored as given. If this regresses, identities split, or a place is
"linked" to a string nobody can resolve.

The identifiers are real: Pleiades 109133 (Lutetia/Paris), Wikidata Q90 (Paris), GeoNames 2988507,
Getty TGN 7008038 -- recorded here as facts, nothing is fetched.
"""

from __future__ import annotations

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.knowledge.authorities import AUTHORITIES, AuthorityIdRefused, authority_of_uri, canonical_uri
from fichero_server.models.knowledge import AuthoritySnapshot, EntityType, KnowledgeEntity

REAL = [
    ("pleiades", "109133", "https://pleiades.stoa.org/places/109133"),
    ("wikidata", "Q90", "http://www.wikidata.org/entity/Q90"),
    ("geonames", "2988507", "https://sws.geonames.org/2988507/"),
    ("tgn", "7008038", "http://vocab.getty.edu/tgn/7008038"),
]


@pytest.mark.parametrize("authority,identifier,uri", REAL, ids=[r[0] for r in REAL])
def test_each_identifier_has_one_canonical_uri_and_reads_back(authority, identifier, uri):
    assert canonical_uri(authority, identifier) == uri
    assert canonical_uri(authority, uri + ("" if uri.endswith("/") else "/")) == uri   # the URI form, trailing slash
    assert authority_of_uri(uri) == (authority, identifier)


def test_the_gazetteers_are_authorities_beside_wikidata():
    assert {key for key, a in AUTHORITIES.items() if a.gazetteer} == {"pleiades", "tgn", "geonames", "whg"}
    assert {"wikidata", "viaf", "loc"} <= set(AUTHORITIES)


@pytest.mark.parametrize("authority,identifier", [
    ("pleiades", "Paris"), ("wikidata", "90"), ("geonames", "2988507abc"), ("tgn", ""),
    ("pleiades", "http://vocab.getty.edu/tgn/7008038"),       # another authority's URI
    ("gazetteer-of-nowhere", "1"),
])
def test_what_is_not_an_identifier_is_refused(authority, identifier):
    with pytest.raises(AuthorityIdRefused):
        canonical_uri(authority, identifier)


def test_a_place_is_linked_to_pleiades_and_a_bad_id_is_refused_before_anything_is_stored(db, client):
    place = KnowledgeEntity(canonical_name="Paris", entity_type=EntityType.location)
    db.save(place)
    db.save(AuthoritySnapshot(authority="pleiades", authority_id="109133", label="Lutetia/Parisii",
                              source_url="https://pleiades.stoa.org/places/109133"))
    linked = client.post("/api/kg/entity-curation/authority/link",
                         json={"entity_id": place.id, "authority": "pleiades",
                               "authority_id": "https://pleiades.stoa.org/places/109133/"})
    assert linked.status_code == 200, linked.text
    refused = client.post("/api/kg/entity-curation/authority/link",
                          json={"entity_id": place.id, "authority": "pleiades", "authority_id": "Paris"})
    assert refused.status_code == 422 and "Pleiades" in refused.text
