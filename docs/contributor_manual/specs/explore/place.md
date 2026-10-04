# Explore: by place — maps, journeys, changing places — Design Spec (#5032)

> Milestone: explore
> Manual: TBD — a section of "Exploring a project": seeing a project's places on a map; why a
> place may be a circle, a region or a question mark rather than a pin; following a diary's
> journeys through a year; laying a scanned historical map over the modern one.
>
> **Status: DRAFT — first pass, 2026-09-20.** Foundation, words and common rules: `explore.md`.

## Intent (the design)

The maintainer's own example sets the target: **a diary's locations mapped over time**. A
researcher chooses a diary, asks for the place map, and sees where the writer was through the
year, can slide or play the year, and can open any stop to the entry that records it. Behind
that sit the same honesty problems as time: a historical place may be known only roughly
("somewhere on the upper Atrato"), may have been renamed, may have moved, and may have belonged
to different jurisdictions at different dates. A pin on a modern map hides all of that.

Lives in: the Library's existing Map view mode (`Views/Library/ViewModes/Dataset/Map/`), and the
knowledge-graph map (`Views/Library/ViewModes/Graph/KGMapView.swift`) promoted from the Reader
to a Library view mode for claims and entities; both MapKit today.

## Prior art

HGIS de las Indias (places and jurisdictions with dates), the World Historical Gazetteer and
its Linked Places format (a GeoJSON extension for places with names and extents that change over
time; the standard to export to), Pleiades and GeoNames as gazetteers to reconcile against,
SlaveVoyages' time-lapse route maps, Kindred Britain's linked geography. The source-model set
already specifies control points that tie a scanned map to the earth
(`source.geo.segment-to-world`, `source.geo.names-a-place`, → #4933); this family draws what that
makes possible and does not restate it.

## What exists

- The claim and entity model holds a point with an uncertainty radius in metres, a named place,
  and a list of evidential places with geometry type, a geographic bounding box, **GeoJSON**,
  basis, confidence, source and rationale (`models/knowledge.py`). Richer than any view uses.
- **Not modelled:** a place whose name, extent or jurisdiction changes over time; a gazetteer;
  a link from a place entity to an outside gazetteer record other than Wikidata enrichment.
- Two map views, both MapKit pins: the dataset Map (a folder's rows with a "lat,lon" attribute;
  rows without a coordinate are counted beneath) and the knowledge-graph map (Reader tab only,
  one document, 500 claims, asserted against inferred drawn differently). No uncertainty
  radius, no regions, no pin clustering, no time, no routes.
- MapKit draws Apple's modern map, fetched from Apple as the researcher pans. No research data
  is sent, but the REGION being looked at is visible to Apple, a modern political map is the
  wrong ground for 1790, and it does not work offline (open; see Open questions below).
- No GeoJSON exporter. Georeferencing a scanned map has an old open issue (#1755) and the
  source-model behaviours above, all [GAP].

## Behaviors

Honest places
- `explore.place.a-place-has-a-shape` — **[PARTIAL]** (#5032) a place is drawn as what is known:
  a point, a circle of uncertainty, a line, a region, or a named area with no coordinates at
  all. The model holds the radius, the bounding box and GeoJSON; both map views draw only pins.
- `explore.place.basis-and-confidence-are-visible` — **[PARTIAL]** (#5032) a place stated in the
  source, a place matched to a gazetteer by a person, and a place guessed by a model are drawn
  differently, and the confidence and asserter controls apply. Asserted against inferred is
  built in the knowledge-graph map only.
- `explore.place.unplaced-is-counted` — **[PARTIAL]** (#5032) items with a place NAME but no
  coordinates, and items with no place at all, are two counts beside the map, each opening to a
  list from which a place can be given. Built only as one count in the dataset Map.
- `explore.place.places-change` — **[GAP]** (#5032) a place entity can hold names, extents and
  jurisdictions each with their own dates, and the map draws the one that held "as of". Needs a
  model change; PROPOSED, not yet ruled (open; see Open questions below).
- `explore.place.gazetteer-link-is-a-claim` — **[GAP]** (#5032) tying a place in the sources to
  a gazetteer record is a statement with an author, a confidence and evidence, like any other;
  a model may suggest, a person decides.

The place map
- `explore.place.map-of-any-set` — **[PARTIAL]** (#5032) a place map can be asked for on a
  folder, a search result, a collection of claims or entities, or one entity, as a Library view
  mode. Built for folder rows; the claims map exists only as a Reader tab.
- `explore.place.one-map` — **[GAP]** (#5032) the dataset map and the knowledge-graph map become
  one drawing, not two code paths.
- `explore.place.pins-gather-when-many` — **[GAP]** (#5032) many marks near each other are drawn
  as one mark with a count that opens to a list; zooming in separates them. This replaces the
  500-claim cap.
- `explore.place.size-and-colour-by-any-field` — **[GAP]** (#5032) a mark's size can say how many
  claims or entries stand behind it, and its colour a chosen field (kind, person, group by
  meaning, asserter).

Over time
- `explore.place.as-of` — **[GAP]** (#5032) the map obeys the shared "as of" control
  (`explore.time.as-of-control`): marks outside the window fade, and it can be played.
- `explore.place.journeys` — **[GAP]** (#5032) for one person or one diary, dated places in
  order are joined as a journey. A leg is drawn as a plain connector between two recorded
  stops, styled so that it cannot be mistaken for a recorded route; when a route IS recorded
  (the river, the road), it can be given and is drawn as such.
- `explore.place.journey-stops-open-the-entry` — **[GAP]** (#5032) choosing a stop or a leg
  opens the entries that place the person there, with the words highlighted in the Source view.
- `explore.place.flows-between-places` — **[GAP]** (#5032) for many people or many movements,
  the map draws flows between places weighted by count (the SlaveVoyages route map), and
  individuals on demand.

The ground
- `explore.place.basemap-is-a-choice` — **[GAP]** (#5032) the ground under the marks can be
  Apple's modern map, a plain ground that needs no network (coastlines and rivers bundled), or
  one of the project's own georeferenced historical maps. The default is a ruling (open; see Open questions below).
- `explore.place.works-offline` — **[GAP]** (#5032) with the plain ground, the place map works
  with no network and sends nothing anywhere.
- `explore.place.historical-map-as-ground` — **[GAP]** (#5032, waits on → #4933) a scanned map
  with control points can be laid under the marks, with its transparency adjustable against the
  modern ground; places labelled on it lead to their place entities.

Out
- `explore.place.geojson-out` — **[GAP]** (#5034) the places of any set leave as GeoJSON (and,
  where places change over time, Linked Places format), each feature carrying its dates, basis,
  confidence, asserter and the citable reference of its evidence, so the work continues in
  QGIS. Rights are applied (`explore.care.rights-apply-everywhere`).

## How it is drawn (decided per kind; RULED 2026-09-20)

**Native is recommended.** The place map is a Library view mode (the existing Map mode, grown).
Two MapKit views already exist; uncertainty circles, regions, journeys and flows are native
overlays; nothing here is easier on the web, and an HTML map would cost
about 500 MB for its WebKit process, as measured on the 16 GB M1 the app is tested on (#4999, #4997)
and would fetch its own tiles from somewhere. In detail: MapKit where a modern or satellite ground is wanted; a native plain ground otherwise.
Flows and journeys are overlays on the same map view. Published saved views are drawn by HTML
from the same data; the publishing basemap must be one the researcher has the right to publish
(Apple's tiles are not; see Open questions below).

## Test matrix (legs this family touches)

Pure Swift (which shape is drawn for which evidence; gathering rule; journey leg styling);
backend (places of a set with evidence ids and the two "unplaced" counts; GeoJSON validates
against the standard); CLI and MCP (GeoJSON export); click-around (choose a stop, the Source
view shows the entry); load (a project's places gather without a cap).

## Open questions for the creative director

Still open, not blocking: the ground a place map stands on, and that Apple's map tiles come from
Apple; places that change, and a gazetteer (now or later?).
