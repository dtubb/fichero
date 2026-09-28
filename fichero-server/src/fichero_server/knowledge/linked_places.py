"""Place entities out as Linked Places Format (maps D9, #4946; `source.geo.linked-places-out`).

LPF is the World Historical Gazetteer's GeoJSON-LD: a Feature per place with several `names`
(toponym, language, citations, `when`), a GeometryCollection whose members each carry their own
`when`, and `links` to gazetteers. The place entity was built in its shape (D6/D7), so this is a
mapping, not a model: names -> toponyms, dated place evidence -> geometries, `same_as` -> exactMatch.

`when` is ISO 8601, which counts years astronomically: a source's historical year is converted
on the way out (Pleiades's -330, 330 BC, is `-0329`) -- stored as written, exported as the standard
says. Nothing here is a second store: the export is worked out from the entity each time.
"""

from __future__ import annotations

import re

from fichero_server.knowledge.places import astronomical_year

LPF_CONTEXT = "https://raw.githubusercontent.com/LinkedPasts/linked-places/master/linkedplaces-context-v1.1.jsonld"
_DATE = re.compile(r"^\s*[+-]?\d{1,6}-(\d{2})-(\d{2})")


def iso8601(value, numbering: str | None) -> str | None:
    """`value` as an ISO 8601 date or year on the astronomical count: a full date keeps its month and
    day (when the source gives them -- Wikidata's `-00-00` does not), a year is signed four digits."""
    year = astronomical_year(value, numbering)
    if year is None:
        return None
    text = f"-{abs(year):04d}" if year < 0 else f"{year:04d}"
    match = _DATE.match(str(value))
    if match and match.group(1) != "00":
        text += f"-{match.group(1)}" + (f"-{match.group(2)}" if match.group(2) != "00" else "")
    return text


def lpf_when(span) -> dict | None:
    if span is None:
        return None
    start, end = iso8601(span.start, span.numbering), iso8601(span.end, span.numbering)
    if start is None and end is None:
        return None
    timespan = {}
    if start is not None:
        timespan["start"] = {"in": start}
    if end is not None:
        timespan["end"] = {"in": end}
    when = {"timespans": [timespan]}
    if span.label:
        when["label"] = span.label
    return when


def _cite(source: str | None) -> list[dict] | None:
    return [{"@id": source}] if source else None


def _drop_none(record: dict) -> dict:
    return {key: value for key, value in record.items() if value is not None}


def _geometry(place) -> dict | None:
    if place.geojson:
        shape = {"type": place.geojson["type"], "coordinates": place.geojson["coordinates"]}
    elif place.lat is not None and place.lon is not None:
        shape = {"type": "Point", "coordinates": [place.lon, place.lat]}
    else:
        return None
    return _drop_none({**shape, "when": lpf_when(place.when), "certainty": "certain" if place.basis.value == "asserted" else "less-certain",
                       "citations": _cite(place.source_document_id and f"urn:fichero:document:{place.source_document_id}"),
                       "fichero:rationale": place.rationale})


def entity_uri(entity_id: str) -> str:
    return f"urn:fichero:entity:{entity_id}"


def place_feature(entity, same_as_uris: list[str]) -> dict:
    """One place entity as an LPF Feature."""
    names = [{"toponym": entity.canonical_name}]
    for name in entity.names:
        names.append(_drop_none({"toponym": name.text, "lang": name.language, "citations": _cite(name.source),
                                 "when": lpf_when(name.when)}))
        if name.romanized:
            # The romanized form is a toponym of its own, in the same language written in Latin script.
            names.append(_drop_none({"toponym": name.romanized,
                                     "lang": f"{name.language}-Latn" if name.language else None,
                                     "citations": _cite(name.source), "when": lpf_when(name.when)}))
    geometries = [g for g in (_geometry(place) for place in entity.place_values) if g is not None]
    return _drop_none({
        "@id": entity_uri(entity.id),
        "type": "Feature",
        "properties": {"title": entity.canonical_name},
        "names": names,
        "geometry": {"type": "GeometryCollection", "geometries": geometries} if geometries else None,
        "links": [{"type": "exactMatch", "identifier": uri} for uri in same_as_uris] or None,
        "descriptions": [{"value": entity.description}] if entity.description else None,
    })


def feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "@context": LPF_CONTEXT, "features": features}
