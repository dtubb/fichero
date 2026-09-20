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
> The milestone does not exist yet; until it does, every [GAP] cites the epic, #5032 (and #5030
> where the map by meaning is meant). Issues are to be cut from the build order below.
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
   is computed by the engine on the researcher's own computer.
3. **Easy to experiment.** A view is tried in a minute on a selection, a folder or a search
   result; it changes nothing in the project; it can be thrown away without trace, kept as
   something that can be run again, compared with another, and exported with its data. These
   are working tools, not museum pieces (though one can be published as such).
4. **Inferred is shown as inferred.** Confidence, method and who asserted it travel with every
   inferred mark and can be filtered on.
5. **Several linked views of one selection, through the panes that exist.** No dashboard, no
   second navigator, no new surface.

The files this will live in are named in each family file. The frame it extends is already in
the app: the Library's view modes (`fichero/fichero/App/ViewDisplayMode.swift`,
`Views/Library/ViewModes/`), the canvas channels (`Views/Library/ViewModes/Canvas/Engine/`), the
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
| `experiments-and-sharing.md` | methods behind one seam, experiments, saved views, comparing, export, publishing, hosted services, care in representation |

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
| Kindred Britain | one dataset as network, timeline and map AT ONCE, linked. In Fichero that is three panes |
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

Reused rather than rebuilt: the Library view-mode dispatch, the canvas's four channels, the
selection and pane model, the search query and its legs, the claim's time and place fields, the
engine's graph routes, the one export record stream, the one audited action layer, the
background-work throttle.

## The words (one meaning each)

| Word | Means |
|---|---|
| **set** | what a view draws: a folder, a whole project, a search result, a hand-made selection, or a collection of entities or claims. A set is always described by something that can be run again (a folder, a query, a list of ids) |
| **view** | one way of drawing a set: table, timeline, place map, network, storyline, arc diagram, map by meaning, distribution, flow |
| **mark** | one drawn thing: a point, a bar, an arc, a line, a band, a row |
| **evidence** | the claims, and through them the places on the page, that a mark was built from. Every mark has evidence |
| **aggregate** | a mark that stands for many things (a bar of 300 entries, a cluster of 2,000 pages). It opens to a list, and the list opens to the ink |
| **channel** | one way a view encodes a fact without moving anything: colour, size or depth, highlight. Already the canvas's word |
| **arrangement** | where items sit in the Canvas and the Space. Already the canvas's word. "By meaning" is an arrangement |
| **method** | a named computation with its settings shown: a projection, a clustering, a labelling, a network layout, a link inference |
| **experiment** | a view of a set made with a method, not yet kept. Throwing it away leaves nothing behind |
| **saved view** | an experiment that was kept: the set's description, the view, the method and its settings. It stores how to make the picture, never the picture |
| **as of** | the moment or period a time-aware view is showing |

The brief says "a saved query plus a recipe". The word **recipe** is already ruled in the source
model to mean a shareable file that makes a WORKFLOW. This set says **method and settings**
instead, so one word keeps one meaning. If the maintainer prefers "recipe" here too, that is a
naming ruling (question 12).

Words taken from the source-model set and used the same way: **project**, **source**,
**segment**, **reading**, **pass**, **campaign**, **Source view**. Until that set lands, "the
place on the page" means a claim's source anchor and excerpt.

## Where it lives (PROPOSED; question 1 is blocking)

The maintainer asked whether this is a new layer or part of the Reader, and wants the answer
argued, not assumed. Weighed against the ratified pane rulings (`ui/modes-to-panes.md`,
`ui/panes-workspaces.md`), the proposal is: **neither. It is not a place.** It is a family of
LIBRARY VIEW MODES and ARRANGEMENTS for sets, plus Reader and Inspector renditions for one
selected thing.

| The thing being looked at | Where its view lives | Why |
|---|---|---|
| a SET (folder, project, search result, entities, claims) | a **Library view mode**, or an arrangement inside Canvas and Space | a view of a set is navigation: things are picked on it and the Source view, Reader and Inspector follow, exactly as they follow the icon grid. Ratified: the Library is always the navigator |
| ONE selected thing (a person's life, one document's people) | a **Reader or Inspector rendition** of that selection | ratified: each surface renders its own rendition of the selected kind. The Reader's per-document graph, timeline and map tabs already work this way |
| several views at once | **panes**, linked | ruled: no dashboard surface |

What each alternative would give up:

- **A new layer (its own sidebar entry or window).** Gives a clear home and a name to teach.
  Gives up: it would be a second navigator, which the pane rulings forbid; it would need its own
  selection, its own search scope and its own chrome, which is the duplicate-code-path problem
  the maintainer has named as a standing worry; and search results, the most useful first set,
  live in the Library.
- **Part of the Reader.** The Reader already draws HTML, so charts would be quick to make. Gives
  up: the Reader shows READINGS of what is selected; a map of 4,000 pages is not a reading of
  anything. Picking things on it would make the Reader a navigator. It would also put every
  chart in a WebKit process (see the cost below).
- **Library view modes (proposed).** Gives up: a single named destination. The name "Explore"
  survives as the name of this spec set, of a group in the View menu, and (PROPOSED) of a
  built-in workspace that opens two or three Library panes beside the Source view.

**One conflict with a ratified ruling, stated plainly.** Kindred Britain's "pick a person and
all three views move" needs Library panes that share a selection. `panes.library.not-linked-to-
each-other` is RULED: Library panes are independent, and linking is explicit
(`panes.library.explicit-link-to-one-preview`, drag-to-connect, awaiting design, #4881). This
set does not reopen that ruling. It asks that the explicit link, when designed, can ALSO join
one Library pane to another, so that a linked group shares one selection and one "as of". Until
then, views work one pane at a time (question 2, blocking for linked views only).

A second thing found: `m2p.kg-graph-retires-as-library-takeover` says the knowledge-graph
timeline and map are already Library view modes on the Entities collection. On disk they are
mounted only in the Reader, for one document (`Views/Reader/Knowledge/DocumentKGSurface.swift`);
entities and claims in the Library are tables only. This set treats the ruling as the intent
and the code as not there yet.

## How it is drawn (PROPOSED; question 3 is blocking)

Two routes, each with a real advantage.

| | Apple native | HTML in a WebKit view |
|---|---|---|
| What exists | Canvas (2D) and Space (3D) with selection, marquee, zoom, animation, four channels; Swift Charts (the KG timeline); MapKit (two map views); a native force-directed graph | the Reader; an Eleventy static-site export |
| Best at | selection that is the app's own selection; animation; the Pencil; 3D; no extra process; accessibility and keyboard for free | very many points (WebGL); mature chart, network and map libraries; **the same code can be published on the web**, which fits the static-site and IIIF publishing vision |
| Cost | each new kind of chart is written by hand; a very large network or scatter may be too heavy | **a WebKit content process measured at about 500 MB** on the maintainer's 16 GB M1, and the machine was starved (#4999, #4997); a message bridge for selection; must never flash white; libraries must be bundled, never fetched |

**Proposed: native in the app, HTML for publishing, and one data contract between them.**

- In the app, every view is native. Arrangements (by meaning, by date) go to the Canvas and
  Space, which already exist. Timelines and distributions use Swift Charts. Storylines, arcs
  and networks are drawn natively for the sizes a researcher works at (a diary year, a person's
  neighbourhood, a search result). This costs no extra process and the Pencil, animation and 3D
  come with it.
- The engine computes every view's DATA once and returns it in one plain shape (marks, their
  positions or values, their evidence ids, how they were made). The native view draws that. The
  **published** form of a saved view is the same data drawn by a small HTML page inside the
  static-site export. So the web advantage is kept where it matters (sharing) without paying
  500 MB while working.
- The WebGL route inside the app is held in reserve for ONE case: a whole-project map or
  network too heavy for the native renderer. It is decided by MEASURING, per family, not by
  habit, and never more than one such WebKit view is alive at a time.

Per family, the proposal and the measured trigger are in each family file and in question 3.

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
- `explore.inferred.filter-by-confidence-and-asserter` — **[GAP]** (#5032, depends on #4868,
  #4869) every view over claims offers two controls: a minimum confidence, and who asserted it
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
- `explore.panes.views-are-library-view-modes` — **[GAP]** (#5032) a view of a set is a Library
  view mode or a Canvas arrangement, mounted from the one dispatch switch; it is never a new
  pane kind, a new sidebar mode or a window of its own.
- `explore.panes.one-thing-is-a-rendition` — **[PARTIAL]** (#5032) a view of ONE selected thing
  is a Reader or Inspector rendition of that selection. Built for a document's graph, timeline
  and map (`DocumentKGSurface.swift`); not built for a person, a place or a claim.
- `explore.panes.linked-views-share-selection-and-time` — **[GAP]** (#5032, waits on #4881)
  Library panes joined by an explicit link share one selection and one "as of"; unlinked panes
  stay independent, as ruled.
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
  the researcher's machine. No view, label or layout calls a hosted service.
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
- `explore.care.rights-apply-everywhere` — **[GAP]** (#5032, waits on #4953) a view never draws,
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
| 4 | **Map by meaning, search results, 2D** | "Arrange by: Meaning" in the Canvas, coloured by group or by which search leg found it | one projection method; one new `CanvasArrangement` case; slice 3's groups as the colour |
| 5 | **Timeline of claims and entries** | the knowledge graph's timeline as a Library view mode for claims and entities, with uncertain dates drawn honestly and binned when large | promote `KGTimelineView`; lift the 500 cap by aggregating |
| 6 | **Place map** | the same for places, with uncertainty radius; then journeys over time | promote `KGMapView`; basemap ruling (question 7) |
| 7 | **People network with a time slider** | a person's or a folder's network "as of", with confidence and asserter controls | an "as of" argument on the engine graph routes; truthful provenance (#4868, #4869) |
| 8 | **Storylines for a diary year**, then arcs | who is with whom, through the year | co-presence from dated claims; a native storyline drawing |
| 9 | **Saved views, compare, publish** | keep, re-run, compare two methods, publish to the static site | the saved-view record (question 4); the HTML drawing of the data contract |
| 10 | **Whole project, 3D, odd ones out, near-duplicates, topics over time** | the larger and rarer uses | cached background layouts; measuring native against WebGL |
| 11 | **Counts, flows, word use across the corpus; hands and certainty** | the distant-reading and hermeneutic views | tables from sources (#5026); the source model (milestone 322) |

Slices 1 to 4 need nothing that is not already on disk. Slices 7 and 11 wait on other work and
say so.

## Test matrix (the set's, DRAFT; each family file names the legs it touches)

| Leg | This set? | Pins |
|-----|-----------|------|
| Pure rule (Swift) | y | arrangement order, binning, asserted-against-inferred drawing rule, "what was left out" counts |
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
Blocking: 1 (where it lives), 2 (linking Library panes), 3 (native, HTML or both), 4 (how a
saved view is stored), 5 (what may ever go to a hosted service).
