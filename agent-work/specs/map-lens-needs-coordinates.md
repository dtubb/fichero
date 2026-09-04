# The map lens has no coordinates to plot (2026-09-04)

Ground truth for Daniel's "the map doesn't really map". Three defects, two of
them client-side and fixed; the third is the one that matters and it is
server-side.

## What already exists

`KGMapView` is a real MapKit map, not a placeholder: pins per located claim,
colour by entity kind, asserted-vs-inferred provenance, tap-to-select
cross-filtering, camera auto-fit. `KGTimelineView` beside it is the same
shape. Both have been there since #1267.

A geocoder exists too — `fichero_server/media/geo.py`: an offline gazetteer of
~35 Spanish-American, Iberian and world cities, falling through to Nominatim
when `online=True`. And `extract_geo` (`workflows/tools/geo_extract.py`) runs
place-name extraction and calls `geo.geocode_places(names, online=...)`.

## Fixed here (client)

1. **Wrong library.** `KGMapView.load()` and `KGTimelineView.load()` both
   resolved `LibraryManager.shared.globalLibrary` — not "the current library"
   but the one holding the reserved global id. Opened on any other library
   they listed the GLOBAL library's claims: no error, no pins, an empty map
   over a corpus full of places. Same defect as #4461 and as the reader's Node
   Graph this morning. Both take the surface's own `EntityService` now.

2. **No document scope in the reader.** `DocumentKGSurface` mounted both
   without `sourceDocumentId`, so a reader tab titled "Map" plotted the first
   500 claims in the LIBRARY — a set the document being read need not be in.
   Both are document-scoped now.

3. **Unplaced places were a count, not a list.** The header said "8 unmapped"
   and left the reader to guess which eight. They are named in a side panel
   now. They are never approximated onto the map: a pin is a claim about where
   something was, and a reader has no way to discover that a confident-looking
   one was a guess.

## NOT fixed — the actual blocker

**Nothing in the extraction pipeline ever writes a coordinate onto a claim.**

- `KnowledgeClaim.claim_geo` is the field the map reads.
- The only caller that passes `claim_geo=` is the manual claim-create route,
  `api/routes/claim/claims.py:491`.
- `_entity_writer.create_claim(...)` accepts `claim_geo` and threads it into
  `EvidentialPlace.lat/lon` — but every extraction path calls it without one.
- `extract_geo` geocodes, and returns its points as TOOL OUTPUT (`geo`,
  `value`, `places`, `unresolved`). Nothing consumes that output to update the
  claims the same run produced.

So `claim_geo` is null for every extracted claim in every library, and the map
is structurally empty no matter which library it asks or how well the
gazetteer covers the corpus. The three fixes above are necessary and not
sufficient.

### The server change this needs

`extract_geo` already holds both halves: `names` (extracted places) and
`points` (geocoded). What is missing is the write-back — for each claim
produced from the same text whose `claim_location` matches an extracted name,
set `claim_geo` to that name's point.

Two constraints from the integrity rule, both non-negotiable for this data:

- **Mark it as geocoded, not attested.** A gazetteer hit is not evidence from
  the manuscript; it is an inference about a name the manuscript contains. The
  model already distinguishes these — `EvidenceBasis` /
  `KGSpatial.provenance`, which the map renders as a dimmed open pin versus a
  solid one. A geocoded point must arrive as `inferred`, never `asserted`, or
  the map will assert a precision the archive never had.
- **Record which geocoder resolved it**, with the queried string. "Condoto" is
  ambiguous across countries; a point with no provenance cannot be checked,
  corrected, or curated later.

## On seeding the gazetteer

The obvious demo shortcut is to add the Marshall corpus's Chocó places —
Condoto, Tamaná, Andagoya, Istmina, Quibdó, Nóvita, Certeguí, Opogodó, Playa
de Oro, Bagadó, Saijá — to `_GAZETTEER`.

**Deliberately not done, and it should not be done this way.** Those
coordinates would come from a language model's recollection, not from a
source. A hand-curated gazetteer is curated BY a human FROM a gazetteer; a
model-recalled one is a set of plausible numbers that will pin a mining claim
a few kilometres into the wrong river valley and look exactly as confident as
a correct one. This app's north star is facts with provenance, and a
demo-shaped exception to that is the one place it would do the most damage —
in front of an audience, over real research data.

Two honest routes to the same demo:

1. **Run `extract_geo` with `online_geocoding: true`.** Nominatim resolves the
   Chocó municipalities today, with a real `display_name` to record as
   provenance. This needs the write-back above and nothing else.
2. **Import a real gazetteer subset.** GeoNames' `CO` extract is public-domain
   and gives verifiable coordinates plus feature codes (so a RIVER — San Juan,
   Atrato, Tamaná — is not pinned as though it were a town, which the point
   model cannot express anyway; `PlaceGeometryType` already has room to say
   so).

Either way the number in the database traces to something outside the model
that produced it, which is the whole point.
