"""The external authorities an entity can be the same as, and each one's CANONICAL URI (maps D2,
#5123; `source.geo.gazetteer-authorities`).

One table, so an identifier has one spelling everywhere it is stored, linked or exported: a gazetteer
link is a `same_as` typed link to this URI (D3), and Linked Places Format and `owl:sameAs` write it.
An identifier that does not fit its authority's pattern is REFUSED, never stored as given -- free
text is not an identity, and a mistyped Pleiades number that happened to be stored would be found
by nobody. An identifier given as its own canonical URI is accepted and read back to the id.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Authority:
    key: str
    label: str
    #: The identifier as the authority writes it.
    pattern: re.Pattern[str]
    #: The canonical URI for an identifier (`{id}`), and a pattern reading one back.
    uri: str
    uri_back: re.Pattern[str]
    gazetteer: bool = False

    def canonical(self, identifier: str) -> str:
        return self.uri.format(id=identifier)


def _authority(key, label, pattern, uri, back, gazetteer=False) -> Authority:
    return Authority(key, label, re.compile(pattern), uri, re.compile(back), gazetteer)


AUTHORITIES: dict[str, Authority] = {a.key: a for a in (
    _authority("wikidata", "Wikidata", r"Q[1-9]\d*", "http://www.wikidata.org/entity/{id}",
               r"https?://(?:www\.)?wikidata\.org/(?:entity|wiki)/(Q[1-9]\d*)/?"),
    _authority("viaf", "VIAF", r"[1-9]\d*", "https://viaf.org/viaf/{id}",
               r"https?://viaf\.org/viaf/([1-9]\d*)/?"),
    _authority("loc", "Library of Congress", r"(?:n[bor]?|sh)\d+", "https://id.loc.gov/authorities/{kind}/{id}",
               r"https?://id\.loc\.gov/authorities/(?:names|subjects)/((?:n[bor]?|sh)\d+)/?"),
    # The gazetteers (ruled 2026-09-27: they live on the place ENTITY).
    _authority("pleiades", "Pleiades", r"[1-9]\d*", "https://pleiades.stoa.org/places/{id}",
               r"https?://pleiades\.stoa\.org/places/([1-9]\d*)/?", gazetteer=True),
    _authority("tgn", "Getty TGN", r"[1-9]\d*", "http://vocab.getty.edu/tgn/{id}",
               r"https?://vocab\.getty\.edu/(?:page/)?tgn/([1-9]\d*)/?", gazetteer=True),
    _authority("geonames", "GeoNames", r"[1-9]\d*", "https://sws.geonames.org/{id}/",
               r"https?://(?:sws\.|www\.)?geonames\.org/([1-9]\d*)(?:/.*)?", gazetteer=True),
    _authority("whg", "World Historical Gazetteer", r"[1-9]\d*", "https://whgazetteer.org/places/{id}",
               r"https?://whgazetteer\.org/places/([1-9]\d*)(?:/.*)?", gazetteer=True),
)}


class AuthorityIdRefused(ValueError):
    """An identifier that does not fit its authority, or an authority this library does not know."""


def normalise(authority: str, identifier: str) -> str:
    """The identifier as its authority writes it, from itself or its canonical URI; refused if it fits neither."""
    found = AUTHORITIES.get(authority)
    if found is None:
        raise AuthorityIdRefused(f"unknown authority {authority!r}; one of {', '.join(sorted(AUTHORITIES))}")
    value = (identifier or "").strip()
    back = found.uri_back.fullmatch(value)
    if back:
        return back.group(1)
    if found.pattern.fullmatch(value):
        return value
    raise AuthorityIdRefused(
        f"{identifier!r} is not a {found.label} identifier (expected like {found.uri.format(id='…', kind='names')})")


def canonical_uri(authority: str, identifier: str) -> str:
    """The one URI an identifier is stored and exchanged as (`AuthorityIdRefused` if it is not one)."""
    found = AUTHORITIES.get(authority)
    value = normalise(authority, identifier)
    if found.key == "loc":
        return found.uri.format(kind="subjects" if value.startswith("sh") else "names", id=value)
    return found.canonical(value)


def authority_of_uri(uri: str) -> tuple[str, str] | None:
    """(authority, identifier) for a canonical (or recognised) URI, or None."""
    for found in AUTHORITIES.values():
        back = found.uri_back.fullmatch((uri or "").strip())
        if back:
            return found.key, back.group(1)
    return None


# ---------------------------------------------------------------------------
# A chosen authority link IS a typed `same_as` link to the canonical URI (maps D3,
# `source.geo.gazetteer-typed-record`): maker, certainty, time and withdraw, several per entity.
# The earlier dict in `entity.metadata["authority_links"]` is migrated into these on open and no
# longer read -- one place answers "which authority is this entity the same as".
# ---------------------------------------------------------------------------

SAME_AS = "same_as"
#: Where a library's malformed earlier entries are kept, named with why, after the migration.
REFUSED_KEY = "authority_links_refused"


def same_as_links(db, entity_id: str) -> list:
    from fichero_server.models.typed_links import TypedLink

    return [link for link in db.query(TypedLink, from_id=entity_id)
            if link.link_type == SAME_AS and link.to_kind == "uri" and link.deleted_at is None]


def authority_links_of(db, entity_id: str) -> list[dict[str, str]]:
    """The entity's live authority links as {authority, authority_id, uri} -- read from typed links only."""
    out = []
    for link in same_as_links(db, entity_id):
        found = authority_of_uri(link.to_id)
        if found:
            out.append({"authority": found[0], "authority_id": found[1], "uri": link.to_id})
    return out


def link_entity(db, entity_id: str, authority: str, identifier: str, *, provenance_kind, created_by,
                certainty: float | None = None, note: str | None = None):
    """The entity's `same_as` link to the authority's canonical URI; the live one when it exists already."""
    from fichero_server.models.typed_links import TypedLink

    uri = canonical_uri(authority, identifier)
    existing = next((link for link in same_as_links(db, entity_id) if link.to_id == uri), None)
    if existing is not None:
        return existing
    link = TypedLink(from_kind="entity", from_id=entity_id, to_kind="uri", to_id=uri, link_type=SAME_AS,
                     directed=False, provenance_kind=provenance_kind, created_by=created_by,
                     certainty=certainty, note=note)
    db.save(link)
    return link


def migrate_authority_links(db, entity) -> list[dict[str, str]]:
    """Turn one entity's earlier `metadata["authority_links"]` into `same_as` links. Idempotent.
    Each entry's maker is who confirmed it (its `EntityMergeAudit` row) when recorded, else the
    library's earlier state (`external_import`, note "earlier authority link"). An entry that fits
    no pattern is REFUSED and kept, named with why, under `REFUSED_KEY` -- never dropped, never
    guessed. Returns the refused entries."""
    from fichero_server.models.knowledge import EntityMergeAudit, ProvenanceKind

    entries = list((entity.metadata or {}).get("authority_links") or [])
    if not entries:
        return []
    confirmed = {}
    for audit in db.query(EntityMergeAudit, target_entity_id=entity.id):
        link = (audit.alias_changes or {}).get("authority_link") if isinstance(audit.alias_changes, dict) else None
        if isinstance(link, dict):
            confirmed.setdefault((link.get("authority"), link.get("authority_id")), audit.created_by)
    refused = []
    for entry in entries:
        authority, identifier = entry.get("authority"), str(entry.get("authority_id") or "")
        try:
            canonical_uri(authority, identifier)
        except AuthorityIdRefused as reason:
            refused.append({"authority": authority, "authority_id": identifier, "reason": str(reason)})
            continue
        maker = confirmed.get((authority, identifier))
        link_entity(db, entity.id, authority, identifier,
                    provenance_kind=ProvenanceKind.human if maker else ProvenanceKind.external_import,
                    created_by=maker, note=None if maker else "earlier authority link")
    metadata = dict(entity.metadata or {})
    metadata.pop("authority_links", None)
    if refused:
        metadata[REFUSED_KEY] = [*metadata.get(REFUSED_KEY, []), *refused]
    entity.metadata = metadata
    db.save(entity)
    return refused


def segments_naming(db, uri: str) -> dict:
    """Every live segment that NAMES a place the given authority URI identifies (maps D3,
    `source.geo.gazetteer-query`): the entities `same_as` it, then the segments that `names` them.
    Any accepted spelling of the URI is read as its canonical form. Nothing is fetched."""
    from fichero_server.models import Segment
    from fichero_server.models.typed_links import TypedLink

    found = authority_of_uri(uri)
    if found is None:
        raise AuthorityIdRefused(f"{uri!r} is not the URI of an authority this library knows")
    canonical = canonical_uri(*found)
    entity_ids = sorted({link.from_id for link in db.query(TypedLink, to_id=canonical)
                         if link.link_type == SAME_AS and link.from_kind == "entity" and link.deleted_at is None})
    segments = []
    for entity_id in entity_ids:
        for link in db.query(TypedLink, to_id=entity_id):
            if link.link_type != "names" or link.from_kind != "segment" or link.deleted_at is not None:
                continue
            segment = db.get(Segment, link.from_id)
            if segment is None or segment.deleted_at is not None:
                continue
            segments.append({"segment_id": segment.id, "document_id": segment.document_id,
                             "entity_id": entity_id, "certainty": link.certainty, "link_id": link.id})
    return {"uri": canonical, "authority": found[0], "authority_id": found[1],
            "entity_ids": entity_ids, "segments": sorted(segments, key=lambda s: (s["document_id"], s["segment_id"]))}
