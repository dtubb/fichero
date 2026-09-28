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
