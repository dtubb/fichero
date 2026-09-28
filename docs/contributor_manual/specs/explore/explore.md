# Explore — seeing a whole project — Design Spec (#5032)

> Milestone: explore
> Manual: TBD — the user manual needs an "Exploring a project" part, written for a researcher:
> the ways to LOOK at a folder, a search result, the people, places and claims of a project
> (by meaning, by time, by place, as a network, as a table); that every mark opens the words on
> the page it came from; that anything inferred says so; and that a view can be tried, kept,
> thrown away, exported and published.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT — first pass, 2026-09-20. This is the FOUNDATION of the
> explore set: the intent, the words, where it lives, how it is drawn, and the rules every view
> obeys. Nothing is approved. Nothing here is built unless tagged [OK] or [PARTIAL].**
> Tags: **[OK]** built and tested · **[PARTIAL]** built, partly proven or not reachable ·
> **[GAP]** intended, never built · **[BROKEN]** code contradicts the rule.
>
> **One milestone for the whole set**: every file in this folder declares `Milestone: explore`.
> GitHub milestone 323. Slices 1 to 4 of the build order have their own issues (#5033 more like
> this, #5034 export what I see, #5035 group my search results, #5036 map by meaning for search
> results; #5038 declares scikit-learn); every other [GAP] cites the epic, #5032, or #5030 for
> the map by meaning, until its slice is cut.
> What the maintainer has ruled is marked RULED. Everything else is PROPOSED until ruled; the
> open decisions are collected in `agent-work/dh-layer/questions-for-the-maintainer.md` and
> summarised at the foot of each file.

## Intent (the design)

A project can already be READ (sources, transcription), THOUGHT about (entities, claims) and
SEARCHED. This set answers the next question: **how else can a researcher navigate, see, explore
and understand what the project holds?** Laid out by meaning; along a line of time; on a map;
as a network of people that changes year by year; as a table with counts; as the lines of a
diary's people crossing through a year.

Five rules hold the whole set together. They are RULED (2026-09-20) and every family file obeys
them:

1. **Always back to the source.** Every mark on every view opens the claims and the places on
   the page it was built from.
2. **Research data does not leave the machine** unless the researcher publishes it. Everything
   is computed by the engine on the researcher's own computer. **No hosted service is used for
   visualisation, ever** (RULED 2026-09-20): doing locally what a hosted embedding-map service
   does is the purpose of the app. Files in standard formats can be exported; what a researcher
   does with a file outside the app is theirs.
3. **Easy to experiment.** A view is tried in a minute on a selection, a folder or a search
   result; it changes nothing in the project; it can be thrown away without trace, kept as
   something that can be run again, compared with another, and exported with its data. These
   are working tools, not museum pieces (though one can be published as such).
4. **Inferred is shown as inferred.** Confidence, method and who asserted it travel with every
   inferred mark and can be filtered on.
5. **Several views of one selection, through the panes that exist.** No dashboard, no second
   navigator, no new surface. How panes link is for a design session, not this set.

The files this will live in are named in each family file. The frame it extends is already in
the app: the Library's view modes (`fichero/fichero/App/ViewDisplayMode.swift`,
`Views/Library/ViewModes/`), the
knowledge-graph views (`Views/Library/ViewModes/Graph/`), the engine's graph, search, vector and
export routes (`fichero-server/src/fichero_server/api/routes/`). The inventory, with paths, is
`agent-work/dh-layer/what-exists.md`.

## The files

| File | Holds |
|---|---|
| `explore.md` (this file) | intent, the words, where it lives, how it is drawn, the rules every view obeys, the build order |
| `meaning.md` | what the vectors can do: more like this, grouped results, odd ones out, near-duplicates, the map by meaning |
| `time.md` | timelines, uncertain dates, the time slider and animation, storylines, arc diagrams, topics over time |
| `place.md` | place maps, uncertain and changing places, journeys over time, historical maps |
| `networks.md` | people and other networks, "as of when", confidence and asserter as controls, export to Gephi |
| `tables-and-counts.md` | the table with facets and counts, distributions, flows, word use across a corpus, the hermeneutic layers |
| `experiments-and-sharing.md` | methods behind one seam, experiments, saved views, comparing, export, publishing, what never leaves the machine, care in representation |

## Prior art / best practices (don't invent from scratch)

The maintainer's references, and what each is a model FOR (full notes in the brief, #5032):

| Reference | What is adopted |
|---|---|
| Underwood, *Distant Horizons* | a project's text as a corpus that can be modelled and compared across time, hand, place and kind, with the evidence one step away |
| China Biographical Database | people, kinship and association as structured data that leaves for Gephi, Pajek and GIS |
| Six Degrees of Francis Bacon | inferred relationships shown as inferred; the confidence threshold is a CONTROL on the view |
| The Digital Panopticon | one life assembled from many records; cohorts as flows; the honest problem of drawing very many lives |
| nodegoat (dynamic networks; temporal data) | every relation has dates; the network is always "as of when"; dates are uncertain, open-ended, periods, relative |
| HGIS de las Indias | places and jurisdictions that change over time; maps tied to sources |
| Kindred Britain | one dataset as network, timeline and map AT ONCE, linked. In Fichero that is three panes; how they link awaits a design session |
| Enslaved.org | publishable, joinable linked open data with provenance on every statement; care in how people are represented |
| SlaveVoyages | the everyday form is a TABLE with facets and summary statistics; charts and maps are made from it; datasets download |
| Nomic Atlas | the map by meaning: zoomable, topic labels that change with zoom, lasso, colour by any field. Hosted, so NOT depended on |
| Retina, Gephi | the cheapest honest network view is to export GEXF and open it elsewhere |
| xkcd 657, D3 arc diagram | storylines and arcs: who is with whom through a year or a volume |

Standards adopted rather than invented: GEXF and GraphML (networks), GeoJSON (places), CSV and
Parquet (tables), IIIF and TEI (sources), RDF with a named JSON-LD context (linked open data),
the factoid model and W3C Web Annotation already used by the knowledge graph. Deliberately
different from every reference above: **the mark leads back to the ink**. Most of those projects
cannot do this, because their data was separated from its sources long ago. Fichero's was not.

Reused rather than rebuilt: the Library view-mode dispatch and its one set of chrome, the
selection and pane model, the search query and its legs, the claim's time and place fields, the
engine's graph routes, the one export record stream, the one audited action layer, the
background-work throttle.

## The words (one meaning each)

| Word | Means |
|---|---|
| **set** | what a view draws: a folder, a whole project, a search result, a hand-made selection, or a collection of entities or claims. A set is always described by something that can be run again (a folder, a query, a list of ids) |
| **view** | one way of drawing a set: table, timeline, place map, network, storyline, arc diagram, map by meaning, distribution, flow. Each is its own Library view mode |
| **mark** | one drawn thing: a point, a bar, an arc, a line, a band, a row |
| **evidence** | the claims, and through them the places on the page, that a mark was built from. Every mark has evidence |
| **aggregate** | a mark that stands for many things (a bar of 300 entries, a cluster of 2,000 pages). It opens to a list, and the list opens to the ink |
| **encoding** | what a mark's colour, size or emphasis says (its kind, its date, who asserted it). Changing an encoding moves nothing |
| **method** | a named computation with its settings shown: a projection, a clustering, a labelling, a network layout, a link inference |
| **experiment** | a view of a set made with a method, not yet kept. Throwing it away leaves nothing behind |
| **saved view** | an experiment that was kept: the set's description, the view, the method and its settings. It stores how to make the picture, never the picture |
| **as of** | the moment or period a time-aware view is showing |

The brief says "a saved query plus a recipe". The word **recipe** is already ruled in the source
model to mean a shareable file that makes a WORKFLOW. This set says **method and settings**
instead, so one word keeps one meaning. If "recipe" is preferred here too, that is a naming
ruling (see the questions file).

Words taken from the source-model set and used the same way: **project**, **source**,
**segment**, **reading**, **pass**, **campaign**, **Source view**. Until that set lands, "the
place on the page" means a claim's source anchor and excerpt.

## Where it lives (RULED 2026-09-20)

**Not a new layer, and not the Reader. Views of a set are LIBRARY VIEW MODES.** New view modes
may be added for them, and a view mode may render HTML where that makes sense.

| The thing being looked at | Where its view lives | Why |
|---|---|---|
| a SET (folder, project, search result, entities, claims) | its own **Library view mode** | a view of a set is navigation: things are picked on it and the Source view, Reader and Inspector follow, exactly as they follow the icon grid. Ratified: the Library is always the navigator |
| ONE selected thing (a person's life, one document's people) | a **Reader or Inspector rendition** of that selection | ratified: each surface renders its own rendition of the selected kind. The Reader's per-document graph, timeline and map tabs already work this way |
| several views at once | **panes** | ruled: no dashboard surface. How panes are linked is NOT decided here; see below |

**The Canvas and the Space are not explore views (RULED 2026-09-20).** The 2D space and the 3D
canvas are a spatial workspace: a node's things laid out PHYSICALLY, by the researcher's own
hand. Exploring feels different: the picture is computed, disposable and re-made. So the explore
views are their OWN view modes. None of them is an arrangement inside the Canvas or the Space,
and none borrows the canvas's arrange, colour, depth and highlight controls. A first draft of
this set proposed "Arrange by: Meaning" as a case of the canvas's arrangement; that is withdrawn.

What the two rejected alternatives would have given up, kept for the record:

- **A new layer (its own sidebar entry or window).** A clear home and a name to teach; but a
  second navigator, with its own selection, search scope and chrome (a duplicate code path),
  and apart from search results, which are the most useful first set.
- **Part of the Reader.** Charts would be quick to make in HTML; but the Reader shows READINGS
  of what is selected, a map of 4,000 pages is not a reading of anything, and picking things on
  it would make the Reader a navigator.

The name "Explore" survives as the name of this spec set and of the group these view modes form
in the Library's view-mode control and the View menu.

**Linked Library panes: a design session first; nothing is ruled here.** Kindred Britain's "pick
a person and the network, the timeline and the map all move" needs Library panes that affect one
another. `panes.library.not-linked-to-each-other` is RULED (Library panes are independent;
linking is explicit; drag-to-connect awaits design, #4881). What is wanted, and does not work
today, is recorded for that session:

- one Library pane UPDATING another: choose an entity in one pane, and the other pane shows the
  pages it appears in (#4881; today a second Library pane's kind and its list can even disagree,
  #5009);
- for this set: a linked group of view modes sharing one selection and one "as of".

Every behaviour in this set that depends on that design is marked **blocked on the pane-linking
design** and is not to be built, or cut into an issue, before the session. Everything else works
one pane at a time.

A second thing found: `m2p.kg-graph-retires-as-library-takeover` says the knowledge-graph
timeline and map are already Library view modes on the Entities collection. On disk they are
mounted only in the Reader, for one document (`Views/Reader/Knowledge/DocumentKGSurface.swift`);
entities and claims in the Library are tables only (#5037; that spec file is not edited on this
branch, so its line keeps its tag until #5037 is worked). This set treats the ruling as the intent
and the code as not there yet.

## How it is drawn (RULED 2026-09-20: decided PER KIND of view, not by one rule)

Two routes, each with a real advantage.

| | Apple native | HTML in a WebKit view, inside a Library view mode |
|---|---|---|
| What exists | Swift Charts (the knowledge-graph timeline); MapKit (two map views); a native force-directed graph; SwiftUI's single-surface drawing | the Reader; an Eleventy static-site export |
| Best at | selection that is the app's own; animation; the Pencil; no extra process; accessibility and keyboard for free | very many points (WebGL); mature layout libraries for networks, storylines, arcs and flows; **the same drawing can be published on the web**, which fits the static-site and IIIF publishing vision |
| Cost | each new kind of drawing, and its layout, is written by hand | **a WebKit content process measured at about 500 MB** on the 16 GB M1 the app is tested on, where the machine was starved (#4999, #4997); a message bridge so that a chosen mark becomes the app's selection; must never flash white; every library bundled, never fetched |

The rules for ANY HTML view mode, whatever the kind: at most ONE such WebKit view alive at a
time across the app; it is released when its view mode is left; its libraries are bundled; its
selection is the app's selection; and it draws the same data the engine gives every other
caller.

**Every view's data has one shape.** The engine computes a view once and returns marks, their
positions or values, their evidence ids and how they were made. A native view mode draws that;
an HTML view mode draws that; the PUBLISHED form of a saved view (RULED: HTML, in the static
site) draws that. This is what lets the choice be made per kind, and changed later, without a
second computation.

Recommended per kind (each family file gives the reasons in full):

| View mode | Recommended | Why |
|---|---|---|
| table, facets, counts, distributions | **native** | the tables exist; Swift Charts draws bars and bins; nothing here needs the web |
| timeline | **native** | Swift Charts already draws the knowledge-graph timeline; binning keeps it small |
| place map | **native** | two MapKit views exist; overlays for uncertainty, journeys and flows are native |
| map by meaning | **native for a search result or a folder** (points drawn on one surface, never a view per point); **HTML with WebGL for a whole project**, if measuring shows the native drawing cannot keep up | the first case is hundreds of points, which needs no 500 MB; the second is tens of thousands of points with labels that change with zoom, which is what the WebGL libraries are for |
| network | **export to Gephi first; native for a neighbourhood or a diary year; HTML (sigma.js, bundled) for a whole project** | small networks are already drawn natively; a whole-project network is where native is weakest and the web libraries strongest |
| storylines, arcs, flows | **HTML is a fair first choice; native if the memory cost is judged too high** | their layouts are hard and already solved in the open web libraries; the sets are small (a year, a volume); they are the views most likely to be published, and the published HTML drawing has to be written anyway. The price is 500 MB while one is open |


## Behaviors — the rules every view obeys

Every family file's behaviours are in addition to these.

Back to the source
- `explore.source.every-mark-has-evidence` — **[GAP]** (#5032) every mark in every view carries
  the ids of the claims, segments or documents it was built from, in the data the engine
  returns. A view that cannot say what a mark was built from does not ship.
- `explore.source.open-evidence-one-step` — **[GAP]** (#5032) choosing a mark selects its
  evidence through the ordinary selection, so the Source view, Reader and Inspector follow as
  they do for any Library selection; the Source view shows the place on the page highlighted.
  No view has its own "detail" window.
- `explore.source.aggregate-opens-to-a-list` — **[GAP]** (#5032) an aggregate mark opens to the
  list of what it stands for, in the ordinary Library list, and each row opens to its ink.
- `explore.source.nothing-silently-left-out` — **[PARTIAL]** (#5032) a view says how many items
  of the set it could NOT draw and why (undated, no place, no vector, restricted), and that
  count opens to the list. Built today only for the dataset Map (rows with no coordinate are
  counted beneath, `DatasetMapView.swift`) and the dataset date facet.

Inferred is shown as inferred
- `explore.inferred.drawn-differently` — **[PARTIAL]** (#5032) anything inferred, approximate or
  predicted is drawn differently from anything stated in a source (hollow against solid, dashed
  against continuous), the same way in every view. Built today only in the knowledge-graph
  timeline and map (`KGTemporalSpatial.swift`, asserted against inferred).
- `explore.inferred.filter-by-confidence-and-asserter` — **[GAP]** (#5032, depends on → #4868,
  → #4869) every view over claims offers two controls: a minimum confidence, and who asserted it
  (a person, a model, a rule). Marks appear and vanish as they move. The asserter control is
  honest only once machine claims stop being stored as a person's.
- `explore.inferred.method-is-shown` — **[GAP]** (#5032) a view made by a method names the
  method and its settings on the view itself, in words a researcher can cite.

Sets, selection and panes
- `explore.set.any-set` — **[GAP]** (#5032) every view can be asked for on a folder, a project,
  a search result, a hand-made selection, or a collection of entities or claims. A view that
  makes no sense for a set (a place map of items with no places) says so; it is not hidden.
- `explore.set.search-scopes-every-view` — **[PARTIAL]** (#5032) an active search narrows what a
  view draws, as it does for the icon grid. Built for the spatial modes
  (`library.search.spatial-modes-share-one-projection`).
- `explore.panes.views-are-library-view-modes` — **[GAP]** (#5032) a view of a set is its OWN Library
  view mode, mounted from the one dispatch switch; it is never a new pane kind, a new sidebar
  mode, a window of its own, or an arrangement inside the Canvas or the Space, which stay the
  researcher's hand-made spatial workspace.
- `explore.panes.html-view-mode-rules` — **[GAP]** (#5032) a view mode drawn in HTML keeps at most
  one WebKit view alive across the app, releases it when the view mode is left, bundles its
  libraries, never flashes white, and makes a chosen mark the app's own selection.
- `explore.panes.one-data-shape` — **[GAP]** (#5032) the engine returns every view's data in one
  shape (marks, positions or values, evidence ids, how it was made), drawn alike by a native
  view mode, an HTML view mode and a published page.
- `explore.panes.one-thing-is-a-rendition` — **[PARTIAL]** (#5032) a view of ONE selected thing
  is a Reader or Inspector rendition of that selection. Built for a document's graph, timeline
  and map (`DocumentKGSurface.swift`); not built for a person, a place or a claim.
- `explore.panes.linked-views-share-selection-and-time` — **[GAP]** (#5032, → #4881; BLOCKED on the
  pane-linking design session) a linked group of view modes shares one selection and one "as
  of". Whether and how Library panes link is not ruled here; unlinked panes stay independent,
  as ruled.
- `explore.panes.one-library-pane-updates-another` — **[GAP]** (→ #4881, → #5009; BLOCKED on the
  pane-linking design session) recorded as wanted and not working today: choosing an entity in
  one Library pane makes another show the pages it appears in. It belongs to the panes spec;
  it is listed here because every linked explore view stands on it.
- `explore.panes.same-chrome` — **[GAP]** (#5032) every new view keeps the Library's one bottom
  bar, one row menu, select-all and drag, as `library.chrome.*` requires of every mode.

Scale and the machine
- `explore.scale.aggregate-not-one-view-per-point` — **[GAP]** (#5032) above a stated size a
  view draws aggregates (bins, clusters, flows) and individuals on demand. No view builds one
  SwiftUI view per point.
- `explore.scale.seconds-for-hundreds` — **[GAP]** (#5032) a set of a few hundred items draws in
  seconds. Larger sets compute in the background, show progress, and can be cancelled.
- `explore.scale.machine-stays-useful` — **[GAP]** (#5032) all computing for this set runs at
  low priority, bounded in cores and memory, through the engine's existing background throttle
  (`core/background_compute.py`), and never starts a second copy of the embedding model.
- `explore.scale.no-wholesale-redraw` — **[GAP]** (#5032) when one item changes, a view updates
  that mark in place.

Local, audited, one code path
- `explore.local.computed-on-this-machine` — **[GAP]** (#5032) every method runs in the engine on
  the researcher's machine. No view, label, group or layout calls a hosted service, under any setting (RULED).
- `explore.local.no-fetched-code` — **[GAP]** (#5032) any drawing library is bundled in the app;
  nothing is fetched at run time.
- `explore.action.reads-write-nothing` — **[GAP]** (#5032) looking at a view writes nothing to
  the project.
- `explore.action.every-write-is-one-audited-action` — **[GAP]** (#5032) keeping a view, pinning
  positions, accepting a suggested merge or split, and publishing are each one typed action in
  the one audited registry, available the same way to the app, the command line and an agent.
- `explore.action.one-path-per-thing` — **[GAP]** (#5032) views read through the existing stores
  and selection, export through the existing record stream, and compute through one method
  seam. No view has its own fetch, its own selection or its own exporter.

Care
- `explore.care.rights-apply-everywhere` — **[GAP]** (#5032, waits on → #4953) a view never draws,
  labels, counts by name or exports what the rights record restricts; what is left out is
  counted (`explore.source.nothing-silently-left-out`).
- `explore.care.people-are-not-only-points` — **[GAP]** (#5032) where people in the sources did
  not choose to be recorded, a view's defaults are chosen with care: see
  `experiments-and-sharing.md`.

## Build order (PROPOSED; smallest useful first; each slice ships alone)

Engine before app. Each slice names what it needs that is not built.

| # | Slice | What the researcher gets | Needs |
|---|---|---|---|
| 1 | **More like this** | from any page or entry: its nearest neighbours by meaning, as an ordinary Library listing | one engine lookup (extends the existing related-documents route); one menu item. No new view |
| 2 | **Export what I see** | the current set as CSV or Parquet; a network as GEXF; places as GeoJSON | three small exporters on the existing record stream. Gives Gephi, Retina and QGIS before any new view is drawn |
| 3 | **Group my search results** | the results list in headed groups with labels | cluster-and-label for a set (scikit-learn, declared). No map |
| 4 | **Map by meaning, search results** | a new "Meaning" view mode: the results as points, like by like, coloured by group or by which search leg found it | one projection method; one new native view mode drawing all points on one surface; slice 3's groups as the colour |
| 5 | **Timeline of claims and entries** | the knowledge graph's timeline as a Library view mode for claims and entities, with uncertain dates drawn honestly and binned when large | promote `KGTimelineView`; lift the 500 cap by aggregating |
| 6 | **Place map** | the same for places, with uncertainty radius; then journeys over time | promote `KGMapView`; basemap ruling (open; see the questions file) |
| 7 | **People network with a time slider** | a person's or a folder's network "as of", with confidence and asserter controls | an "as of" argument on the engine graph routes; truthful provenance (#4868, #4869) |
| 8 | **Storylines for a diary year**, then arcs | who is with whom, through the year | co-presence from dated claims; a native storyline drawing |
| 9 | **Saved views, compare, publish** | keep, re-run, compare two methods, publish to the static site | the saved-view record (open; see the questions file); the HTML drawing of the data contract |
| 10 | **Whole project, odd ones out, near-duplicates, topics over time** | the larger and rarer uses | cached background layouts; measuring the native drawing against an HTML (WebGL) view mode |
| 11 | **Counts, flows, word use across the corpus; hands and certainty** | the distant-reading and hermeneutic views | tables from sources (#5026); the source model (milestone 322) |

Slices 1 to 4 need nothing that is not already on disk. Slices 7 and 11 wait on other work and
say so.

## Test matrix (the set's, DRAFT; each family file names the legs it touches)

| Leg | This set? | Pins |
|-----|-----------|------|
| Pure rule (Swift) | y | binning, asserted-against-inferred drawing rule, "what was left out" counts |
| Availability (Swift) | y | each view is reachable from the Library's view-mode control for the sets it serves |
| Backend (pytest) | y | every method returns marks WITH evidence ids and its own method and settings; deterministic for a fixed seed |
| MCP | y | an agent can run the same experiment and export |
| CLI | y | one command exports the current set's table, vectors or network |
| Click-around (XCUITest, Mac) | y | choose a mark → the Source view shows the place on the page |
| iPhone / iPad | later | not in the first slices |
| Load (#4634) | y | bounded, cancellable, machine stays useful; stated size at which a view aggregates |

Hard gate for the set: **the same experiment gives the same result from the app, the command
line and an agent**, and **no mark without evidence**.

## Documentation matrix

| Audience | This set? | Lives in |
|---|---|---|
| User | y | the user manual's "Exploring a project" part (the maintainer's own; TBD) |
| Contributor | y | this folder |
| AI / agent | y | MCP tool descriptions for neighbours, experiments and exports |
| Scripter | y | CLI `--help` for the same |
| Reference | y | generated capability reference |

## Preview harness, accessibility identifiers, UX completeness

Each view ships a `#Preview` drawn from fixture data in the engine's data contract, so its
drawing rules (hollow against solid, aggregates, what was left out) can be seen and
screenshotted without a running engine. Identifiers follow `explore.<view>.mark.<id>`,
`explore.<view>.control.<name>`; the tables are filled per slice when a slice is specified for
building, and are [MISSING] until then. Every chart needs a non-visual equivalent: the table of
the same marks is that equivalent, and is always one step away.

## Open questions for the creative director

Full text, defaults and reasons: `agent-work/dh-layer/questions-for-the-maintainer.md`.
RULED 2026-09-20: where it lives; drawing decided per kind; no hosted service for
visualisation. For a DESIGN SESSION: linking Library panes. Still open, not blocking: whether a
saved view is a saved search that remembers its view; the place map's ground (Apple's map tiles
come from Apple).
