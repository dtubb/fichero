# Source Model — Maps and georeference — Design Spec (#5120)

> Milestone: source-model
> Manual: TBD — part of the "How Fichero represents a source" section: how a scanned map is tied
> to the earth by control points, how a place named on any page is tied to a gazetteer, and what
> leaves Fichero for Allmaps, QGIS or a web map.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model: read `source-model.md`
> first (the rulings and the words), then `segments-and-geometry.md` (the segment this slice
> extends). This file is the data-model home for georeferencing that `ui/library-view-modes.md`
> says is missing (#5120). It owns **no screen**: the map view is left to a future UI spec (see
> "Out of scope"). Every behaviour below is **[GAP]** with its issue unless it says otherwise.

## Intent

A historical map is a source like any other: a page with ink on it. What makes it a map is that
some points on it can be tied to places on the earth. Once they are, three things become
possible that a researcher needs: the sheet can be laid over a modern map; any segment drawn on
it (a road, a parish boundary, a label) can say where it is in the world; and a place named on
it, or on any page of any source, can be tied to a shared gazetteer so it can be found, counted,
mapped beside other sources and published as Linked Open Data.

This slice answers four questions the archive model had left soft (#5120), and each answer is a
behaviour below:

1. A **ground control point** (GCP) is a first-class segment, not a by-product of a stored
   transform. The transform is **worked out** from the GCPs.
2. A **place** is tied to a gazetteer by a **typed identifier**, never free text, with candidates,
   confidence and a chosen one.
3. The **coordinate reference system** (CRS) is always explicit: every coordinate arrives with
   an EPSG code, and is **stored in WGS 84 (EPSG:4326)** (ruled 2026-09-27, #5124). "Lat/lon"
   alone is never enough.
4. **IIIF Georeference Annotations** go in and come out through the format harness, tested on
   real files other people made, as PAGE, ALTO and TEI already are.

The same data model also has to carry what the wider research pipeline needs: place names and
boundaries that change over time, places described relative to other places in prose, and export
of places and movements to GeoJSON and a spatial database. Those are specified here too, as data;
how they are drawn is not.

## Prior art (what this builds on, and what it does not invent)

- **IIIF Georeference Extension** (`https://iiif.io/api/extension/georef/`, context
  `http://iiif.io/api/extension/georef/1/context.json`). A W3C Web Annotation with motivation
  `georeferencing`: its **target** is the image (or canvas) plus an SVG selector for the part that
  is the map (the "resource mask"); its **body** is a GeoJSON FeatureCollection in which each
  Feature is one GCP (`properties.resourceCoords` in pixels, `geometry` a WGS 84 Point) and an
  optional `transformation` (`polynomial` with an order, `thinPlateSpline`, `helmert`,
  `projective`). The unit exchanged is the **GCP**, not the fitted transform. That settles
  question 1: a model that stored only a transform could not write this format.
- **Allmaps** (MIT; `github.com/allmaps/allmaps`) reads and writes these annotations and is the
  natural partner the way eScriptorium is for PAGE XML. Its parser accepts two dialects: the
  published extension (`resourceCoords`, the georef context) and an earlier one (`pixelCoords`,
  a target of type `Image`, the anno + GeoJSON-LD contexts). Real files exist in both.
- **Mapwarper** and the **QGIS Georeferencer** exchange GCPs as small tables (pixel x, pixel y,
  map x, map y; QGIS's `.points` file names the CRS in a header line). Again: GCPs, not
  transforms.
- **GDAL** world files (six numbers: an affine transform, no CRS; the CRS travels in a `.prj`
  beside it) and **GeoTIFF** (which can carry GCPs as tie points and the CRS as GeoKeys without
  the image being warped).
- **GeoJSON** (RFC 7946) is WGS 84 longitude/latitude only. Anything in another CRS needs a
  format that carries one: **GeoPackage** (the OGC SQLite format QGIS opens; SpatiaLite is its
  sibling).
- **Linked Places Format** (LPF, the World Historical Gazetteer's GeoJSON-LD): a place has
  several **toponyms** and several **geometries**, each with a `when` (a time span) and a
  citation. This is the established answer to "names and boundaries change over time", and this
  spec adopts its shape rather than inventing one.
- **Gazetteers**, already catalogued in `kg/kg-enrichment.md`: GeoNames (modern), Pleiades
  (ancient), Getty TGN (historical), Wikidata (hub). This spec adds the **World Historical
  Gazetteer** (WHG), which that catalogue lacks and which is built for exactly this material.
- **EPSG** codes name a CRS. EPSG:4326's official axis order is latitude, longitude; GeoJSON
  and IIIF write longitude, latitude. Stating the order is part of stating the CRS.

**What this deliberately does not invent.** A second reconciliation system (the KG has one); a
second link record (the source model has one: `TypedLink`); a second geocoder (`media/geo.py`
exists); a second exporter (the formats harness and `export_service.py` exist).

## What exists today (read on disk, 2026-09-27)

- **No georeferencing at all.** Nothing in `fichero-server/src/` stores a GCP, a transform or a
  CRS. There is no GeoJSON writer, no DuckDB spatial extension, no PROJ.
- **Coordinates on claims and entities**: `GeoPoint` (`models/knowledge.py`: `lat`, `lon`,
  `precision_m`, `place_name`) on a claim's `claim_geo`, and `EvidentialPlace` (points, regions,
  paths and sets; `lat`, `lon`, `geo_bbox`, `geojson`, `basis`, `confidence`, source fields) on
  entities. **Neither names a CRS**; both mean WGS 84 by assumption. `anchors.py` already keeps
  `geo_bbox` apart from image rectangles by name, which this spec keeps.
- **A geocoder, not a gazetteer link**: `media/geo.py` resolves a place *name* to a point from a
  small offline table, then (opt-in) Nominatim, and says which tier answered (#4668). It returns
  coordinates, never an identity.
- **Authority reconciliation for entities** (`api/routes/kg/entity_curation.py`): an
  `AuthoritySnapshot` is a locally cached record of an external authority (`wikidata`, `viaf`,
  `loc`) fetched only by an explicit, opt-in refresh; candidates are found by matching an
  entity's name and aliases against cached snapshots **without fetching**; a person (or an agent,
  as itself) confirms one with the audited action `entity.link_authority`, which appends
  `{authority, authority_id}` to `entity.metadata["authority_links"]` and writes an audit row.
  Pinned by `fichero-server/tests/unit/security/test_external_authority_reconciliation.py`.
  **What it lacks for places**: no gazetteer is an allowed authority; a candidate has no
  confidence and is not kept; a rejected candidate is not remembered; a link is a dict in
  `metadata`, not a typed record that can be queried.
- **The typed link** (`models/typed_links.py`): one record with type, direction, maker and
  certainty, and a `names` type ("Names" / "Is named by") already in the vocabulary. Its ends can
  be a segment, note, document, claim or canvas item, **not a KG entity**.
- **Maps in the app**: `DatasetMapView.swift` and `KGMapView.swift` (MapKit) plot points from
  entities and datasets. They draw no scanned map.

## The design

### A control point is a segment (question 1)

A **ground control point** is a **point segment** on one image of a page, in a pass, with a
maker and a certainty like any other segment. Its **reading** is a world coordinate: a point, a
CRS, and optionally how precise the person was ("to the nearest 50 m"). A GCP is therefore
corrected alone (move the pixel end, retype the world end, withdraw it) as one audited, undoable
action, and nothing else changes.

The set of GCPs that georeferences a map is a **pass** (a "georeferencing pass"). Two people's
georeferencings of one sheet are two passes, both kept; which one is used follows the project's
working-pass rule, as for any layout. A machine may propose GCPs (matching road junctions to a
modern map, say); they arrive in a machine pass and are shown as unchosen until a person chooses,
as the source model rules.

The pass also holds the **mask**: an area segment saying which part of the image is the map (not
the title cartouche, the margin or the scale bar). A sheet with two maps on it (an inset of the
town beside the county) has two masks, each with its own GCPs; the GCPs belong to a mask by a
typed link, not by being inside it.

The **transformation type** (affine, i.e. polynomial order 1; polynomial 2 or 3; thin-plate
spline; Helmert; projective) is a property of the pass, chosen by a person, with a default
(polynomial 1, which needs 3 GCPs and is what a world file can hold).

The **transform is worked out**, never the master. It is computed from the pass's GCPs and its
transformation type. A stored copy is a cache that names the version of the GCP set it came from
and is thrown away when that changes. From it come each GCP's **residual** (how far the fitted
transform misses that point, in pixels and metres), which is how a person finds the one GCP that
was typed wrong.

This **replaces** the "geographic anchor kind plus warp transform" of the archival plan (P11): a
geographic place is not a new kind of anchor on the image; the segment's anchor stays on the
image, and its place in the world is **worked out** through the georeferencing pass.

GCPs are measured on one image. On another image of the same page (a rescan, a deskewed copy)
they apply only through a known alignment, the rule `segments-and-geometry.md` already has.

### Any segment's place in the world

On a georeferenced map, any segment can be asked for its place in the world: the engine applies
the working georeferencing pass's transform to the segment's shape and answers with a shape in
world coordinates, its CRS, which pass and transform version produced it, and an error estimate
from the residuals. The answer is **worked out** and never stored as the segment's truth; a
corrected GCP changes every answer at once, which is the point.

A segment outside the mask is answered "outside the map", never extrapolated silently.

### The coordinate reference system is always said (question 3)

- **Stored in WGS 84 (ruled 2026-09-27, #5124).** Every world coordinate Fichero stores is in
  EPSG:4326. The maintainer's ruling overrides this spec's earlier recommendation, which was to
  store coordinates as entered.
- **The input CRS is still always said.** A coordinate cannot be converted correctly without
  knowing what it arrived in, so the CRS it arrived in is an EPSG code (or, for a CRS with no EPSG
  code, its WKT2 text) and is never assumed. A GCP typed in a national grid (British National
  Grid, EPSG:27700) is converted to WGS 84 when it is written. The stored coordinate records the
  CRS it came from and the conversion used, because a datum shift is not exact and the choice is
  a fact about the result.
- **Exchange default: EPSG:4326**, written longitude then latitude wherever the format does so
  (GeoJSON, IIIF). The axis order is recorded, not assumed.
- **Unknown is a value.** A file that arrives with no CRS (a world file with no `.prj`) is
  imported with CRS **unknown**. It cannot be converted, so its numbers are held unconverted and
  marked unknown: they can be looked at, but they are not a stored world coordinate and cannot be
  overlaid or exported as geographic data. Once a person declares the CRS, they are converted and
  stored. It is never taken to be WGS 84.
- Existing `GeoPoint` and `EvidentialPlace` values are WGS 84 by assumption today. They are
  **declared** EPSG:4326 by an additive schema change that states the assumption, rather than
  left implicit.
- CRS conversion needs PROJ and its database. The engine ships sandboxed and **cannot download
  code at run time**, so PROJ (through `pyproj`, or through DuckDB Spatial, which bundles it)
  ships with the app at build time.

### Places and gazetteers (question 2)

A **place segment** is any segment that names a place: a label on a map, a place name in a line
of a letter, a cell in a register. It is tied to a **place entity** in the knowledge graph with
the existing typed link `names`, with a maker and certainty. The gazetteer identity belongs to
the **entity**, not to each segment: ten letters that name Popayán are ten `names` links to one
entity, and that entity is reconciled once. **Ruled 2026-09-27 (#5123):** the gazetteer link lives
on the PLACE ENTITY and never on a segment. WHG, Pleiades, Getty TGN and Wikidata all connect to
that one entity, and the entity may point to the segments that mention it.

The entity's gazetteer identity **extends the authority seam that exists** rather than building
a second one:

- The allowed authorities gain the gazetteers: `whg`, `pleiades`, `tgn`, `geonames`, alongside
  `wikidata` (which is already there). Each authority has one **canonical URI form**
  (`https://pleiades.stoa.org/places/<n>`, `http://vocab.getty.edu/tgn/<n>`,
  `http://www.wikidata.org/entity/Q<n>`, `https://sws.geonames.org/<n>/`, WHG's place URI), and
  an identifier that does not fit its authority's pattern is refused. Free text is never a
  gazetteer identity.
- **Candidates are kept**, each with its authority, identifier, label, the snapshot it came
  from, how it was found (exact name, alias, a machine's match) and a **confidence**. A person
  (or an agent, recorded as itself) **chooses one**; the others stay as rejected candidates so
  the same wrong match is not offered again. Choosing is the existing audited action, extended.
- A place may be the **same as** entries in several gazetteers (Pleiades and Wikidata for one
  Roman town). Those are several chosen links, not a conflict.
- Lookups stay **opt-in and cached**: candidates are found from local snapshots; only an explicit
  refresh goes to the network, behind the existing external-authority switch. Reading a place
  never fetches.
- The geocoder in `media/geo.py` is a different thing: it answers "roughly where is a place of
  this name", not "which place is this". Its answers are labelled machine guesses and never
  become a gazetteer link without a person's choice.

Because the link is typed, "every segment in the library that names Pleiades place 579885" is
one query, from the app, MCP and the command line; and the reconciliation leaves as Linked Open
Data (the entity `owl:sameAs` its gazetteer URIs; Linked Places Format for the place itself).

### Places over time

Names and boundaries change. The place entity adopts the Linked Places Format shape:

- **Several names**, each with a language, a script, a time span when it was used (as far as
  known) and the source that attests it. "Santa Fe de Bogotá" and "Bogotá" are two names of one
  place, not two places.
- **Several geometries**, each with a time span and a source. An administrative area (a parish,
  a province, a colonial *audiencia*) is an **area in world coordinates** with a span; asking for
  a place **as of a date** gives the geometry valid then, or says there is none. A boundary drawn
  on a georeferenced map is a segment; its worked-out world shape can be **adopted** as one of
  the place's geometries, and remembers the segment and map it came from.
- A georeferenced map carries **the date it depicts** (which can differ from when it was drawn
  or printed), so what it shows can be placed in time.
- Time spans use the model's existing evidential dates (`EvidentialDateRange`), not a new kind
  of date.

### Places described in words

"Two leagues north of the river", "half a day's ride from the mission". A relative description
is stored as what it is: a claim with an **anchor place** (the river, itself a place entity), a
**relation** (north of, near, between, upstream of), a **distance as written** with its unit
("two leagues"), and a certainty. It resolves to an **area of uncertainty**, never a point.

A historical unit is kept as written together with **the conversion used** (which league: the
Castilian *legua* differs from others by region and period), so the resolved area can be
recomputed when a better conversion is chosen. It is never folded into metres silently.

Resolving a description to an area is a **worked-out thing**; the description is the record.

### Formats (question 4)

These are readers and writers on the one formats harness (`formats/harness.py`), obeying every
rule in `formats-and-training.md`: import arrives as a new pass; nothing unrecognised is thrown
away; export is validated; every export has a loss report; round trip is tested; real files from
other software, never files written to look like them.

- **IIIF Georeference Annotation**, in and out. In: both dialects Allmaps accepts. Out: the
  published extension (`resourceCoords`, the georef/1 context, a `SpecificResource` target with an
  SVG selector for the mask, the transformation type). A georeferencing pass round-trips: GCPs,
  mask and transformation type come back; what the format cannot carry (makers, certainty,
  residuals, a CRS other than WGS 84, which it does not allow) is in the loss report, and a GCP
  entered in another CRS is written in its worked-out WGS 84 form with that said.
- **Validation.** The extension publishes a JSON-LD context and normative prose, and no JSON
  Schema was found when this was written. Validation is therefore a checker written from the
  extension's normative requirements, vendored with its source URL and date, the same way the
  XML schemas are vendored. If an official schema appears, it replaces the checker.
- **GCP tables**: the QGIS `.points` file and Mapwarper's GCP CSV, in and out, with the CRS
  carried (QGIS) or declared on import (Mapwarper).
- **World file and GeoTIFF**, out (and world file in): a world file with its `.prj` for an
  affine pass; a GeoTIFF of the unwarped image with the GCPs as tie points and the CRS as GeoKeys.
  Neither needs the image to be warped.
- **GeoJSON**, out: places, place segments in world coordinates, and **entity movements**
  (claims that put a person at a place at a time, as LineStrings or timed Points), each Feature
  carrying the stable reference back to its segment, claim or entity. WGS 84 only, as RFC 7946
  requires; anything else goes to GeoPackage.
- **GeoPackage**, out: the same layers in any CRS, for QGIS.
- **KML**, in and out: what Mapwarper exports a warped map as (a `GroundOverlay` with its
  `LatLonBox`). It is the one XML format in this family and an OGC standard with a published XSD,
  so our KML export is validated against the vendored schema like PAGE and ALTO (licence first).
  **Import and export whatever Allmaps and Mapwarper use** (maintainer, 2026-09-27): IIIF
  Georeference for Allmaps, and the GCP CSV and KML for Mapwarper. Each is tested on REAL exports
  from that software, not only on files we write.
- **Linked Places Format**, out: place entities with their names, geometries, spans and gazetteer
  links, for WHG and other gazetteers.
- **DuckDB Spatial** for spatial questions inside the engine (which places fall inside this
  province as of 1780; which letters name a place within ten km of this one). The extension is
  shipped at build time; `INSTALL spatial` at run time is not possible in a sandboxed build.

**The real sample, and how its licence was checked.** Two files from the Allmaps repository
(`github.com/allmaps/allmaps`, branch `main`):

| File | Size | Licence | What it exercises |
|---|---|---|---|
| `packages/annotation/test/input/annotation.1.body-transformation-thin-plate-spline.json` (blob `044d48c1`, last commit `02cf4afd`, 2023-08-21) | 1,693 bytes | **MIT**, © Bert Spaan (`packages/annotation/LICENSE.md`, and `"license": "MIT"` in that package's `package.json`) | The published dialect: georef/1 context, `SpecificResource` target with an `ImageService2` source and a four-point SVG mask, a `thinPlateSpline` transformation, GCPs as `resourceCoords` + WGS 84 Points (a plan of Paris). |
| `apps/cli/test/input/annotations/7a69f9470b49a744-resourceCrs.json` (blob `b17998e6`, last commit `6c5e737b`, 2025-09-05) | 2,534 bytes | **MIT**, © Manuel Claeys Bouuaert (`apps/cli/LICENSE.md`, and `"license": "MIT"` in `apps/cli/package.json`) | The earlier dialect: an `AnnotationPage`, a target of type `Image` with a fourteen-point mask, GCPs as `pixelCoords` (a plan in Delft). |

The repository root declares no licence (GitHub reports none); each package declares its own,
and both packages these files live in declare MIT in a `LICENSE.md` and in `package.json`. That
was checked **before** naming them, from licence metadata only. MIT may sit in this AGPL
repository and its permanent history. Only the annotation JSON is vendored; the map images it
points at belong to the libraries that hold them and are **not** fetched or vendored (the tests
need the pixel and world coordinates, not the pixels). The IIIF extension's own `context.json` is
**not** vendored until its licence is confirmed: the `IIIF/api` repository declares none. A
further real file from a different producer (a Mapwarper or QGIS export under a permissive
licence) is still wanted, so one producer's reading of the format is not the only one tested.
Each vendored file gets a row in `tests/unit/formats/fixtures/PROVENANCE.md`.

## Out of scope (left to a future map-view UI spec)

- The **map view**: placing GCPs by clicking on the scan and on a basemap, the side-by-side
  editor, residuals shown on the map, opacity and swipe.
- **Warping the image** on the client (WebGL or Metal), **tile servers** and serving warped
  tiles, basemap choice and its licensing.
- The **3D globe** of #1755 (RealityKit).
- Drawing places, boundaries and movements over a basemap in the Library's `.geoMap` mode (today
  `DatasetMapView` / `KGMapView`); what they draw is defined here, how they draw it is not.

A UI spec for the map surface should cite this file for every record it shows; it adds no
fields.

## Behaviors

Control points and the transform
- `source.geo.gcp-is-a-segment` — **[PARTIAL]** (#4933) a ground control point is a point segment on
  one image, in a pass, with a maker and certainty, whose reading is a world point with a CRS.
  **Built engine-side:** a `control-point` segment's world end is a `ControlPointPlace` record (`georef.place`), on the Allmaps Paris file's own points (`fichero-server/tests/unit/api/test_georeference.py::test_a_real_maps_control_points_place_any_segment_on_the_earth`). No screen yet: the app has no control-point tool or map view. A file's points still cannot be imported into a library: that refusal (#5122) can now be lifted onto this model.
- `source.geo.gcp-corrected-alone` — **[PARTIAL]** (#4933) moving, retyping or withdrawing one GCP is
  one audited, undoable action that changes that GCP's record and no other.
  **Built engine-side:** moving the pixel end is `segment.update`; retyping the world end supersedes that point's place alone and ⌘Z/⇧⌘Z swap them (`fichero-server/tests/unit/api/test_georeference.py::test_retyping_one_control_point_changes_it_alone_shows_up_in_its_residual_and_undoes`). A person denied the page cannot touch it (`fichero-server/tests/unit/api/test_georeference.py::test_a_person_denied_the_page_cannot_place_or_withdraw_its_control_points`). No screen yet: the app has no control-point tool or map view.
- `source.geo.georef-is-a-pass` — **[PARTIAL]** (#4933) a map's GCPs, mask and transformation type
  form one georeferencing pass; two georeferencings of one sheet are two passes, and the
  working-pass rule chooses between them.
  **Built engine-side:** the pass holds the points, masks and type (`fichero-server/tests/unit/api/test_georeference.py::test_a_real_maps_control_points_place_any_segment_on_the_earth`). With two georeferencings and none chosen the engine says so rather than picking; `pass.choose_working` chooses (`fichero-server/tests/unit/api/test_georeference.py::test_a_machines_control_points_are_unchosen_and_two_georeferencings_are_not_picked_between`). **Missing:** a point names its mask by a field (`mask_segment_id`), not a typed link.
- `source.geo.mask` — **[PARTIAL]** (#4933) the part of an image that is the map is an area segment in
  the pass, and a sheet with several maps has several masks each with its own GCPs.
  **Built engine-side:** `mask` area segments in the pass, one fit per mask when there are several (`fichero-server/tests/unit/api/test_georeference.py::test_a_real_maps_control_points_place_any_segment_on_the_earth`). **Missing:** a test with two masks on a real sheet.
- `source.geo.transform-is-derived` — **[PARTIAL]** (#4933) the transform is worked out from the
  pass's GCPs and transformation type; a stored copy names the GCP-set version it came from and
  is discarded when that changes.
  **Built engine-side:** worked out on every read, never stored, and every answer names `gcp_set_version`, which changes with any point or the type (`fichero-server/tests/unit/api/test_georeference.py::test_a_real_maps_control_points_place_any_segment_on_the_earth`). No stored copy exists, so none needs discarding.
- `source.geo.transformation-type` — **[PARTIAL]** (#4933) the transformation type is an explicit
  choice on the pass, defaulting to affine, and too few GCPs for the chosen type is refused with
  the number needed.
  **Built engine-side:** `georef.set_type` (polynomial 1/2/3, Helmert, projective, thin-plate spline; default polynomial 1, undoable) (`fichero-server/tests/unit/api/test_georeference.py::test_a_real_maps_control_points_place_any_segment_on_the_earth`); too few refused with the number needed (`fichero-server/tests/unit/api/test_georeference.py::test_too_few_control_points_for_the_type_is_refused_with_the_number_needed`). No screen yet: the app has no control-point tool or map view.
- `source.geo.residuals` — **[PARTIAL]** (#4933) every GCP reports its residual under the current
  transform in pixels and metres, so a wrong one can be found.
  **Built engine-side:** metres, the image fraction, and pixels when a rendition records its size (`fichero-server/tests/unit/api/test_georeference.py::test_a_real_maps_control_points_place_any_segment_on_the_earth`). **Found on a real map:** with few points the residuals show the SET is wrong but not WHICH point. On the Paris sheet (four points, an affine) the mistyped point had the smallest residual, and leaving each out in turn did not single it out either (`fichero-server/tests/unit/api/test_georeference.py::test_retyping_one_control_point_changes_it_alone_shows_up_in_its_residual_and_undoes`). Finding the one wrong point needs more points than the type needs; the Inspector should say so rather than rank points.
- `source.geo.machine-gcps-unchosen` — **[PARTIAL]** (#4933) GCPs a machine proposes arrive in a
  machine pass and are labelled unchosen until a person chooses them.
  **Built engine-side:** a workflow's pass answers `chosen: false` until a person chooses it (`fichero-server/tests/unit/api/test_georeference.py::test_a_machines_control_points_are_unchosen_and_two_georeferencings_are_not_picked_between`). No screen yet: the app has no control-point tool or map view.
- `source.geo.gcp-other-image` — **[PARTIAL]** (#4933) GCPs measured on one image apply to another
  image of the page only through a recorded alignment, and otherwise Fichero says they do not.
  **Built engine-side (the refusal half):** a segment on another image is refused by name (`fichero-server/tests/unit/api/test_georeference.py::test_a_machines_control_points_are_unchosen_and_two_georeferencings_are_not_picked_between`). **Missing:** using a recorded alignment.

A segment's place in the world
- `source.geo.world-shape` — **[PARTIAL]** (#4933) on a georeferenced image any segment's world shape
  is answered with its CRS, the pass and transform version used and an error estimate, and is
  never stored as the segment's truth.
  **Built engine-side:** `GET /api/georef/segment/{id}/world` answers GeoJSON with the CRS, axis order, pass, type, `gcp_set_version` and an RMS error (none for a thin-plate spline, which is exact at the points) (`fichero-server/tests/unit/api/test_georeference.py::test_a_real_maps_control_points_place_any_segment_on_the_earth`). No screen yet: the app has no control-point tool or map view.
- `source.geo.outside-the-mask` — **[PARTIAL]** (#4933) a segment outside the map's mask is answered
  "outside the map", never extrapolated.
  **Built engine-side:** answered `outside_the_map` with no geometry (`fichero-server/tests/unit/api/test_georeference.py::test_a_real_maps_control_points_place_any_segment_on_the_earth`).

The coordinate reference system
- `source.geo.crs-explicit` — **[PARTIAL]** (#4933) every coordinate arrives with its CRS as an EPSG
  code or WKT2, and a write that names no CRS is refused (or held as unknown, below).
  **Built engine-side:** every place names its CRS; EPSG:4326 must also say its axis order (`fichero-server/tests/unit/api/test_georeference.py::test_the_crs_is_always_said_converted_to_wgs84_or_held_unknown`).
- `source.geo.crs-stored-as-wgs84` — **[PARTIAL]** (#4933; ruled on #5124) a coordinate is converted to
  WGS 84 (EPSG:4326) and stored in it, recording the CRS it arrived in and the conversion used.
  **Built engine-side for WGS 84 input only:** stored as lon/lat with the CRS, the numbers as typed, the axis order and the conversion (`fichero-server/tests/unit/api/test_georeference.py::test_the_crs_is_always_said_converted_to_wgs84_or_held_unknown`). Any other CRS is refused by name until PROJ ships (`proj-at-build`).
- `source.geo.crs-exchange-default` — **[PARTIAL]** (#4933) EPSG:4326 is the exchange default and the
  axis order written is recorded, never assumed.
  **Built engine-side:** the world answer is EPSG:4326, lon,lat, and says so (`fichero-server/tests/unit/api/test_georeference.py::test_a_real_maps_control_points_place_any_segment_on_the_earth`). **Missing:** the exports.
- `source.geo.crs-unknown` — **[PARTIAL]** (#4933) data imported without a CRS is marked unknown and
  cannot be overlaid or exported as geographic data until a person declares one.
  **Built engine-side:** `unknown` is held unconverted, shown, never fitted (`fichero-server/tests/unit/api/test_georeference.py::test_the_crs_is_always_said_converted_to_wgs84_or_held_unknown`); placing it again with a CRS declares it. **Missing:** overlay and export refusals, since neither exists yet.
- `source.geo.crs-declared-on-existing` — **[GAP]** (#4933) existing `GeoPoint` and
  `EvidentialPlace` coordinates are declared EPSG:4326 by an additive schema change.
- `source.geo.proj-at-build` — **[GAP]** (#4933) CRS conversion uses PROJ shipped with the app at
  build time and never downloads code at run time.

Places and gazetteers
- `source.geo.place-segment-names-entity` — **[GAP]** (#4933) a segment that names a place is
  joined to a KG place entity by a typed `names` link with a maker and certainty.
- `source.geo.gazetteer-authorities` — **[GAP]** (#4933) WHG, Pleiades, Getty TGN and GeoNames are
  authorities beside Wikidata, each identifier is stored in its canonical URI form, and one that
  does not fit its authority's pattern is refused.
- `source.geo.gazetteer-candidates` — **[PARTIAL]** (#4933) candidates for an entity come from
  locally cached authority snapshots without fetching, and a chosen one is recorded by an
  audited action. Built for Wikidata, VIAF and LoC by exact name or alias match
  (`fichero-server/tests/unit/security/test_external_authority_reconciliation.py`, its tests
  "refresh is opt-in and cache-only matching" and "authority link is persisted and refresh
  failure is loud"; cited by file because they are `async def` and the pipeline's test index
  reads only `def`); **missing**: gazetteer
  authorities, a confidence and a match method on each candidate, candidates kept after the
  choice, and rejected candidates remembered so they are not offered again.
- `source.geo.gazetteer-typed-record` — **[GAP]** (#4933) a chosen gazetteer link is a typed,
  queryable record with maker, certainty and time, not a dict in entity metadata, and several
  chosen links to different gazetteers are allowed.
- `source.geo.gazetteer-query` — **[GAP]** (#4933) every segment that names a given gazetteer
  place is one query, answering the same from the app, MCP and the command line.
- `source.geo.gazetteer-offline` — **[GAP]** (#4933) reading or querying places never fetches;
  only an explicit refresh behind the external-authority switch goes to the network.
- `source.geo.geocoder-is-not-identity` — **[GAP]** (#4933) a geocoder hit is labelled a machine
  guess of coordinates and never becomes a gazetteer link without a person's choice.

Places over time and in words
- `source.geo.names-over-time` — **[GAP]** (#5120) a place entity holds several names, each with
  a language, a script, a time span and the source that attests it.
- `source.geo.geometry-over-time` — **[GAP]** (#5120) a place holds several geometries each with a
  time span and source, and asking for a place as of a date returns the one valid then or says
  there is none.
- `source.geo.boundary-from-map` — **[GAP]** (#5120) a boundary segment's worked-out world shape
  can be adopted as a place geometry that remembers the segment and map it came from.
- `source.geo.map-depicts-date` — **[GAP]** (#5120) a georeferenced map carries the date it
  depicts, separate from when it was made.
- `source.geo.relative-place` — **[GAP]** (#5120) a relative description is stored as an anchor
  place, a relation, a distance as written and a certainty, and resolves to an area of
  uncertainty, never a point.
- `source.geo.historical-units` — **[GAP]** (#5120) a historical distance unit is kept as written
  with the conversion used, so the resolved area is recomputed when the conversion changes.

Formats
- `source.geo.iiif-georef-in` — **[PARTIAL]** (#4946, → #5125; the library half → #5122) a IIIF
  Georeference Annotation in either dialect Allmaps accepts imports as a new georeferencing pass with
  its GCPs, mask and transformation.
  **Built: the format reads both dialects** (`formats/iiif_georef.py`). A GCP becomes a
  `control-point` segment with a normalised `point` and a WGS 84 `world`. The mask becomes a `mask`
  area segment. Each GCP names its mask in `foreign["georef:mask"]`, because the spec ties them by a
  typed link and the harness has no links, so nesting is not used to fake it. The transformation is
  the page's. Pinned on both real files:
  `fichero-server/tests/unit/formats/test_iiif_georef.py::TestReadingThePublishedDialect::test_the_gcps_are_point_segments_with_both_ends`,
  `::TestReadingTheEarlierDialect::test_pixel_coords_are_read_and_the_size_comes_from_the_svg`.
  **Not built: into a library.** Nothing in a library can yet hold a GCP's world end, so the import
  is **refused by name** (422, citing #5122) instead of keeping the pixel end and dropping the place
  on the earth
  (`fichero-server/tests/unit/formats/test_import_into_library.py::TestAGeoreferencingFileIsRefusedByName::test_it_is_refused_with_the_reason_and_nothing_is_written`).
  Before that refusal existed, the same file was refused as having shapes "outside the page", which
  was true of nothing in it.
- `source.geo.iiif-georef-out` — **[PARTIAL]** (#4946, → #5125; the library half → #5122) a
  georeferencing pass exports as a georef/1 annotation that passes the vendored checker, with a loss
  report naming what it could not carry.
  **Built format-side:** the published dialect is written, one Annotation per mask (an
  AnnotationPage when there are several), and every write passes the checker, which the harness runs
  (`fichero-server/tests/unit/formats/test_iiif_georef.py::TestWriting::test_every_real_file_exports_as_the_published_dialect`,
  `::TestWriting::test_two_masks_become_two_annotations_each_with_its_own_gcps`,
  `::TestTheChecker::test_an_invalid_export_is_no_file`). Losses are named: segments that are not
  GCPs or masks, and the plain image URL when converting the earlier dialect
  (`::TestWriting::test_converting_the_earlier_dialect_names_what_it_did_not_write`). A missing
  pixel size is refused rather than invented. **The checker** is written from the extension's
  normative text (https://iiif.io/api/extension/georef/, read 2026-09-27). Each rule quotes its
  sentence in the code, and each is fired once by `::TestTheChecker`. Not built: a pass from a
  library, which has no GCPs to give until #5122.
- `source.geo.iiif-georef-round-trip` — **[OK]** (→ #5125) the two vendored Allmaps files import,
  export and import again with the same GCPs, mask and transformation type, less what the loss
  report names (`fichero-server/tests/unit/formats/test_iiif_georef.py::TestWriting::test_the_round_trip_keeps_gcps_mask_and_transformation`,
  format to format. Through a library it waits on the GCP model, which `iiif-georef-in` tracks).
  **Found on the way:** the earlier-dialect file (Delft) **fails the published checker**. It has no
  georef context and uses `pixelCoords`. That is true of the file, and it is why the reader is
  tolerant and the writer strict
  (`::TestReadingTheEarlierDialect::test_the_published_checker_rejects_it_for_the_stated_reasons`).
- `source.geo.gcp-tables` — **[GAP]** (#4946) GCPs go in and out as a QGIS `.points` file and a
  Mapwarper GCP CSV with the CRS carried or declared.
- `source.geo.world-file-geotiff` — **[GAP]** (#4946) an affine pass exports as a world file with
  its `.prj`, and any pass as a GeoTIFF of the unwarped image with GCP tie points and the CRS.
- `source.geo.kml` — **[GAP]** (#4946, → #5125) a warped map goes in and out as Mapwarper's KML
  `GroundOverlay`. Our export validates against the vendored OGC KML schema, and the tests use real
  Mapwarper exports (licence first).
- `source.geo.geojson-out` — **[GAP]** (#4946) places, place segments and entity movements export
  as RFC 7946 GeoJSON, each Feature carrying its reference back to its segment, claim or entity.
- `source.geo.geopackage-out` — **[GAP]** (#4946) the same layers export as a GeoPackage in any
  CRS.
- `source.geo.linked-places-out` — **[GAP]** (#4946) place entities export as Linked Places Format
  with names, geometries, time spans and gazetteer links.
- `source.geo.duckdb-spatial` — **[GAP]** (#4946) spatial questions in the engine use DuckDB
  Spatial shipped at build time, never installed at run time.
- `source.geo.fixtures-licensed` — **[GAP]** (#4946) every vendored geographic fixture is real
  output from other software with a provenance row naming its source, licence and fetch date, and
  none is under a non-commercial or share-alike licence.

## Changes this spec asks of other specs

For the archive lane to apply; this file edits none of them. **Applied 2026-09-27**, all seven. The link-end request became a new behaviour, `source.link.end-is-entity` [GAP]. The point shape was already built (#4925), so it became a pointer.

- **`segments-and-geometry.md`, "Maps and plans" and the three `source.geo.*` bullets**
  (`control-points`, `segment-to-world`, `names-a-place`): point each at this file, where it is
  refined into `gcp-is-a-segment`, `world-shape` and `place-segment-names-entity`. Either retire
  the three in favour of these ids or keep them as umbrellas that cite them; do not keep both as
  independent behaviours.
- **`segments-and-geometry.md`, Links, and `source.link.typed`**: a link end can be a **KG
  entity** (`LinkEndKind` gains `entity`), so a place segment can name a place entity. Today the
  ends are segment, note, document, claim and canvas item.
- **`segments-and-geometry.md`, Shape**: a point shape is required (already listed as what the
  anchor must gain); GCPs are its first user.
- **`archival-data-model-plan.md`, section 3** ("geographic: lat/lon + warp transform") **and P11**:
  a geographic place is not an anchor kind; a segment's world place is worked out through a
  georeferencing pass of GCP segments, with an explicit CRS. The 5a table's P11 row should name
  this file.
- **`formats-and-training.md`**: `source.format.geo-in` / `geo-out` point at this file's Formats
  behaviours; the formats table's last row adds IIIF Georeference Annotation, GCP tables,
  GeoPackage and Linked Places Format; the W3C/IIIF row's "control points for maps" points here.
- **`kg/kg-enrichment.md`**, the gazetteer catalogue: add the **World Historical Gazetteer**, and
  note that place reconciliation is specified in this file.
- **`ui/library-view-modes.md`**, around lines 352-355 and 444: the data model for #1755 now has a
  home (this file); the map **surface** is still homeless until a map-view UI spec exists.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | n | (no screen in this slice) | |
| Availability (Swift) | n | | |
| Backend (pytest) | y | GCPs, derived transform, residuals, CRS rules, gazetteer links, time-bounded places | to be written: test_georeference.py (backend api tests) |
| Formats harness (pytest) | y | IIIF georef in/out/round trip on the Allmaps files; GCP tables; world file; GeoJSON; GeoPackage; LPF | to be written: test_iiif_georef.py (formats tests) |
| MCP | y | the gazetteer query and GCP actions route | `fichero-mcp/tests/test_mcp_full.py` |
| CLI | y | import/export of the geo formats; the gazetteer query | `fichero-cli/tests/` |
| Click-around (XCUITest, Mac) | n | (future map-view UI spec) | |
| iPhone / iPad | n | (future map-view UI spec) | |
| Load (#4634) | y | worked-out world shapes for every segment of a large map sheet stay bounded | `fichero-server/tests/perf/` |

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y (later, with the UI spec) | maintainer's manual |
| Contributor | developer docs | y | this spec |
| AI / agent | MCP tool description | y | `fichero-mcp/**` |
| Scripter | CLI `--help` | y | `fichero-cli/**` |
| Reference | capability/endpoint reference | y | generated |

## Accessibility identifiers and UX completeness

None: this slice has no screen. The future map-view UI spec owns them.

## Open questions for the creative director

1. ~~Where does a gazetteer identity live?~~ **Ruled 2026-09-27 (#5123): on the place entity,
   never on a segment.** This is what was recommended here: a place is reconciled once however
   many pages name it, and each gazetteer (WHG, Pleiades, Getty TGN, Wikidata) connects to that
   one entity.
2. ~~Store coordinates as entered, or normalise to WGS 84 on write?~~ **Ruled 2026-09-27 (#5124):
   stored in WGS 84.** The input CRS stays explicit, because converting correctly depends on it.
   The recommendation here had been "as entered", and the ruling overrides it. The design and
   `source.geo.crs-stored-as-wgs84` now follow the ruling.
3. PROJ's database is several megabytes. Ship it through `pyproj`, or through DuckDB Spatial
   (which bundles PROJ and GDAL and also gives GeoPackage writing)? Recommended: DuckDB Spatial,
   one native dependency for queries, CRS and GeoPackage, subject to its size in the bundle.
