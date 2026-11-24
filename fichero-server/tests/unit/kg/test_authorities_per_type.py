"""`kg.enrich.per-type` (#4758): an authority is offered only for the entity types it serves, so a
place is never offered VIAF and a person is never offered a gazetteer."""

from __future__ import annotations

from fichero_server.knowledge import authorities
from fichero_server.knowledge.authorities import AUTHORITIES
from fichero_server.models.knowledge import EntityType


def authorities_for(entity_type):
    fn = getattr(authorities, "authorities_for", None)
    assert fn is not None, "authorities.authorities_for does not exist"
    return fn(entity_type)


def test_a_place_is_offered_the_gazetteers_and_wikidata_but_not_viaf():
    keys = authorities_for(EntityType.location)
    assert set(keys) == {"wikidata", "pleiades", "tgn", "geonames", "whg"}


def test_a_person_is_offered_viaf_and_loc_but_no_gazetteer():
    keys = authorities_for(EntityType.person)
    assert set(keys) == {"wikidata", "viaf", "loc"}
    assert not any(AUTHORITIES[k].gazetteer for k in keys)


def test_an_organization_is_offered_what_a_person_is():
    assert set(authorities_for(EntityType.organization)) == set(authorities_for(EntityType.person))


def test_a_type_nothing_serves_but_wikidata_gets_only_wikidata():
    assert authorities_for(EntityType.citation) == ["wikidata"]
