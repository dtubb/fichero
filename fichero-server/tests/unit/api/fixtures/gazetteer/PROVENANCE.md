# Gazetteer and authority recordings -- provenance

Real authority records, recorded once and replayed; no test fetches them (maps D4, #5123,
`source.geo.gazetteer-candidates`). They are authority snapshots, not interchange formats, so they
live here and not beside the format fixtures (where the export validator would count them as
unrecognised inputs).

| File | Source | Licence | Recorded | What it is for |
|---|---|---|---|---|
| `pleiades_109126_lutetia.json` | `https://pleiades.stoa.org/places/109126/json`, recorded 2026-09-28 | **CC BY 3.0**, © The Creators (the record's own `rights` field) | as fetched | A gazetteer place record (maps D4, `source.geo.gazetteer-candidates`): Lutetia, with fifteen names, each with its language and a start/end year (`Paris` in `fr` from 1700), and dated locations. Recorded once; no test fetches it. |
| `wikidata_search_paris.json` | `https://www.wikidata.org/w/api.php?action=wbsearchentities&search=Paris&language=en&format=json&limit=5`, recorded 2026-09-28 | **CC0** (Wikidata's data licence) | as fetched | The answer Fichero's own Wikidata refresh asks for, replayed through `_fetch_wikidata_snapshots`: five records: four labelled `Paris` (the city Q90; Paris, Texas; a family name; a plant genus), so choosing one must reject its namesakes, and Paris Saint-Germain FC, which the search found and an exact-name match does not. |
| `wikidata_Q842763_north_magnetic_pole.json` | `https://www.wikidata.org/wiki/Special:EntityData/Q842763.json`, recorded 2026-09-28 | **CC0** (Wikidata's data licence) | as fetched | A place whose location CHANGES over time (maps D7, `source.geo.geometry-over-time`): the North Magnetic Pole, ten coordinate statements (`P625`) each dated by point in time (`P585`) -- Ross's 1831 fix at 70.08°N 96.78°W, then 2001 to 2025 -- several with references. Pleiades almost never dates one place's geometries differently, and the Linked Places Format sample is CC BY-SA, so this is the real, permissively licensed record of a moving place. |
