# KG Rendering — what a name, a statement, its when and its where look like — Design Spec

> Manual: TBD — the knowledge-graph part of the user manual needs one section that says what a
> reader sees: a card for a name, a sentence for a statement, a date and a place as part of the
> sentence, a timeline and a map for many of them, and how to get from any of these to the page.
>
> **Status: DRAFT — first pass, 2026-11-20, from a code review of the Swift app.** An AREA spec
> for the render layer only. The data model is `kg-entities-and-statements.md`; the entity pane is
> `kg-entity-inspector.md`; the tables are `kg-tables.md`; the paragraph is
> `kg-readable-representation.md`; the views on many items are `explore/time.md`,
> `explore/place.md` and `explore/networks.md`; search is `ui/search.md`; chat is
> `ui/research.md`. This spec does not repeat them. It holds the rules they share and the
> research flows that cross them, and it tags each by what the code does today.
>
> No milestone is declared yet; the manager names one when the spec is approved.
>
> Tags: **[OK]** built and checked in the code · **[PARTIAL]** built in part, or built and not
> reachable · **[GAP]** not built · **[BROKEN]** the code contradicts the line. The issues
> filed from this review (milestone kg-rendering) are listed at the end.

## Intent (the design)

The engine holds names (entities), statements (subject, verb, object) and, on each statement,
its qualifiers: when it happened, where it happened, who says so, how sure, and where on the
page it was read. The app draws these. It decides nothing about them.

Three rules follow, and most of what is wrong today breaks one of them.

1. **A thing is drawn as what it is.** A person, a place, an organisation and an event are
   names and may be nodes. A date is not a name. It is the WHEN of a statement, so it is drawn
   on the statement, on a time axis, or as a filter, and never as a node or a row among the
   names. A place is both: a name with its own card, and the WHERE of a statement, drawn on the
   statement and on a map.
2. **Every drawn statement is a door to its page.** A sentence, a table row, an edge, a mark on
   the timeline, a pin on the map and a citation in an answer all open the same thing: the page,
   with the passage lit in the text and its region lit on the image.
3. **What the machine guessed looks different from what a person confirmed**, in the same way on
   every surface, and one action on the spot turns the first into the second.

## Prior art

- **Apple Photos, People and Places.** A person is a card with a key face, a name and a count;
  an unsure match is a question with two buttons ("Same person?"), answered in place, and the
  answer is kept. Places is a map with gathered pins that open the items. Dates are never a
  collection of things; they are the axis (Years, Months, Days). We adopt all three.
- **Contacts card.** One card per person: the name, then labelled fields, each a link to what it
  does. Unknown fields are absent, not empty. We adopt this for the entity card, with authority
  fields (coordinates, life dates, other names, picture) labelled by where they came from.
- **Spotlight.** One field, results grouped by kind (people, places, documents), the best hit
  first, Return opens it, and a preview shows why it matched. We adopt grouping by kind.
- **Tinderbox.** Meaning from position; attributes are shown ON a note (badges, key attributes),
  not as more notes; a timeline view lays the same notes on a time axis. This is the model for
  the 2D canvas (`modes-to-panes.md`, the Canvas family): a date is an attribute that places a
  note, not a note.
- **Recogito.** Annotation on the source is the unit: a name marked on the text or the image,
  tied to a gazetteer record that the reader confirms or rejects from a short candidate list
  with a map preview. We adopt the confirm-or-reject card with kept candidates (→ #5123).
- **Nodegoat.** The same objects seen as a network, on a map and in time, with dates and places
  held on the relation between objects, and a time slider that filters all three. We adopt
  "when and where live on the relation".
- **Wikidata statement model.** A statement has a value plus qualifiers (point in time, start,
  end, location) and references. The engine already stores `time_start`, `time_end`,
  `time_precision`, a place scope and `place_values` on a claim; the app's views must read
  these and not the object phrase.

## What exists today (checked in the code, 2026-11-20)

- **Entity card.** `EntityDigestContent` (`Views/Inspector/Knowledge/EntityDigestView.swift`)
  draws name, kind, description, a "Biography" paragraph of statement sentences, "Appears In"
  and "Source Annotations". It draws no authority data.
- **Graph.** `ForceDirectedGraphView` (+`Render`, `GraphModel.swift`) draws one focus entity and
  its neighbours to 1–3 hops from `GET /api/kg/graph/neighborhood/{id}`. It is mounted in one
  place: the Reader's Graph view of one document (`DocumentKGSurface.swift`).
- **Timeline and map.** `KGTimelineView` and `KGMapView` read `timeStart` and `claimGeo` from
  claims and draw stated values solid and inferred ones hollow (`KGTemporalSpatial.swift`).
  Both are mounted only in the Reader, scoped to one document (→ #5037).
- **Tables.** `EntitiesTableView` (Name, Type, Claims, Authority, Curation) and
  `ClaimsTableView` (Subject, Verb, Object, Date, Source, Confidence, Provenance), opened from
  the sidebar's Entities and Claims rows (`SidebarKnowledgeRows.swift`).
- **Reader.** The transcript is engine-served HTML in a web view; names are lit and clickable
  (`entitySelected`), and a focused claim scrolls to its span
  (`DocumentKGWebPaneCoordinatorMacOS.swift`).
- **Search.** One toolbar field with Ask or Keyword; results are document rows with one excerpt
  each (`ContentView+SearchResults.swift`, `SearchSnippetHighlighter.swift`).
- **Chat.** `MessageCard.swift` draws an answer and a "Sources" list.
- **Not reachable.** `EntityDetailView`, `EntityDigestView`, `ClaimSummaryCardView` and
  `SpeakerComparisonView` have no host since the KG browser retired (→ #4828). With them went
  the only authority-link sheet, the claim review queue, aliases, entity notes and claims
  grouped by source.

## Behaviors

### A. Dates and places are qualifiers, not nodes

- `kg.render.date-is-never-a-node` — **[PARTIAL]** (#5032, #6772, #6768) the graph draws names only.
  Built: `GraphSimulation.buildNodes` makes no node for an id with the `literal:` prefix and keeps
  no edge to one. The app filters on that id prefix until the engine marks literal edges itself
  (#6768, not on main when this was written); the neighbour limit still does not count literal
  edges, which is the engine half. Tests: `fichero/Tests/Unit/general/Views/Library/GraphSimulationNamesOnlyTests.swift`::rebuildMakesNoNodeForALiteral,
  `fichero/Tests/Unit/general/Views/Inspector/KnowledgeGraphInspectorSectionTests.swift::testEpistemologyReducerDropsSubjectToLiteralEdge`.
  Was: a statement whose object is not a known name comes back from the engine as an edge to
  `literal:<object phrase>` (`api/routes/kg/graph.py`, "always keep literal-object edges"), and
  `GraphSimulation.buildNodes` (`GraphModel.swift`) adds a node for each one. Measured on a
  scratch project: one person with five statements (three with a date as object, one with a
  thing, one with a place name) draws one real neighbour and four literal nodes, three of them
  dates. The literal nodes are grey circles, the same mark as an entity of kind Other
  (`drawNodes`, `ForceDirectedGraphView+Render.swift`), and they are not counted against the
  neighbour limit.
- `kg.render.literal-node-tap-is-safe` — **[OK]** (#5032, #6772) choosing any mark in the graph
  never produces an error. Built: the tap hit-test skips `literal:` ids, `entityFocusId(forTapped:)`
  returns no focus for one, and `load()` ignores a literal `selectedEntityId`, so the graph never
  asks the engine for a `literal:` neighbourhood. Tests: `fichero/Tests/Unit/general/Views/Library/GraphSimulationNamesOnlyTests.swift`::aTappedLiteralIdNeverBecomesTheFocus.
  Was: `handleTap` focuses the tapped node's id whatever it is; for a
  literal node the graph then asks the engine for the neighbourhood of `literal:…`, the engine
  answers 404 ("Entity not found", measured), and the graph is replaced by an error line.
- `kg.render.when-is-on-the-statement` — **[PARTIAL]** (#5032, #6773) wherever a statement is drawn
  as a sentence, a row or an edge, its date is drawn with it, in one form: the date as written
  when there is one, else the normalised span, with a mark when it was inferred. Built: the
  Claims table has a Date column and the inline editor edits start, end and precision
  (`ClaimPatchFields.inline`). Not built: the neighbourhood edge carries no time or place field
  at all (`NeighborhoodEdge`), so the graph cannot label an edge with its date; the entity
  card's sentences carry no date; the document inspector does not draw one.
- `kg.render.where-is-on-the-statement` — **[GAP]** (#5032, #6773) the same for the place a
  statement happened at: drawn with the statement, as a link to the place's card when the place
  is a known name. The inline editor has no place field, so a wrong place cannot be corrected
  where it is seen.
- `kg.render.dates-are-not-a-kind-of-name` — **[BROKEN]** (→ #5008, #6774) no list of names
  has a "Dates" group. Today the document inspector's knowledge section groups by kind with a
  synthetic `date` kind made by the engine for statements whose subject is a date
  (`api/routes/document/inspector.py`; `EntityKind.date`, `KnowledgeGraphSupport.swift`), so
  dates sit as rows beside People and Places. The intended drawing: those statements are listed
  under their real subject with the date as the qualifier; the document's dates are offered as
  a small timeline strip at the head of the section, each mark opening its statement.
- `kg.render.graph-shows-chosen-kinds` — **[GAP]** (#5032, #6774; the control is
  `explore.network.kinds-of-node`) the graph has a kinds control (People, Places,
  Organisations, Events, Keywords) and remembers it. Today the legend lists kinds and filters
  nothing; the comment in `ForceDirectedGraphView.swift` says kinds are filtered "upstream",
  and its one host passes every entity of the document. The default is people, organisations
  and places; events and keywords are off until asked for.
- `kg.render.first-focus-is-a-person` — **[GAP]** (#5032, #6774) with nothing chosen, the graph
  opens on the document's most connected person, else its most connected name. Today it opens
  on the first entity in the list whatever its kind (`load()`, `entities.first`).
- `kg.render.an-object-that-is-not-a-name-stays-in-the-sentence` — **[PARTIAL]** (#5032, #6772, #6773) a
  statement whose object is a phrase ("sold a share of the mine") is still seen from the graph:
  the focus node's card lists its statements, and the count of them is a badge on the node. It
  is not drawn as a node. Built: no node for the phrase, and the count of such statements per
  subject (`literalStatementCounts`) drawn as a badge beside the node. Not built: the edge label
  with its date, which waits for the time and place fields on `NeighborhoodEdge` (#6773).
  Tests: `fichero/Tests/Unit/general/Views/Library/GraphSimulationNamesOnlyTests.swift`::aStatementWithALiteralObjectIsCountedOnItsSubject.

### B. One mark for sure and unsure, and correcting in place

- `kg.render.unsure-looks-the-same-everywhere` — **[PARTIAL]** (#1765, #6775) one vocabulary on
  every surface: confirmed by a person, read by a model (with its band), inferred, rejected.
  Built: the approval badge and confidence band on inspector claim rows
  (`EntityKindRow+ClaimBlock.swift`, `ClaimCurationBadge.swift`), Confidence and Provenance
  columns in the Claims table, solid and hollow marks on the timeline and map. Not built: the
  entity card's biography sentences, the graph's edges and the Reader's lit names carry no
  mark at all, though the edge payload already has `confidence` and `epistemic_status`.
- `kg.render.bands-come-from-the-engine` — **[PARTIAL]** (#1765, #6775) where the line between low,
  medium and high falls, and what counts as inferred, is the engine's answer. Today the app
  holds the thresholds (`ConfidenceBand.band`, 0.4 and 0.75) and the stated-or-inferred rule
  (`KGTemporal.provenance`, `KGSpatial.provenance`), which is logic in the app.
- `kg.render.correct-where-you-see-it` — **[PARTIAL]** (#4833) a statement can be corrected from
  the sentence or row it is seen in, without opening another window. Built: the "[Edit]" run in
  the inspector digest and the Claims table's Edit (`InlineClaimEditor`, `EditClaimSheet`).
  Not built: from the entity card's biography on iPhone, from a graph edge, from a timeline
  mark or a map pin.
- `kg.render.a-correction-is-shown-as-kept` — **[GAP]** (#1765, #6775) after a person corrects a
  statement, it is drawn as theirs (the confirmed mark, their name and the day on hover or
  long-press) and the earlier reading is one step away. The engine records this
  (`workflows/curation_guard`, called from the claim patch route); no reachable view draws who
  made a statement (`ClaimSummaryCard+Provenance.swift` did, in the unreachable card).

### C. The entity card and authority data

- `kg.render.card-shows-authority-fields` — **[GAP]** (→ #5123, → #4759) a name linked to an
  authority record shows what the record gives, each field labelled with its source and
  visibly apart from what the project's own pages say: other names, a description, life dates
  for a person, coordinates and a small map for a place, a picture when the record has one,
  and the record's id as a link out. Today `EntityDigestContent` draws none of these.
- `kg.render.authority-is-a-link-in-the-table` — **[PARTIAL]** (→ #5123) the Entities table's
  Authority column shows "WIKIDATA · Q…" as text, parsed in the app from the entity's metadata
  (`EntityTableRow.authorityLabel`). Intended: a typed field from the engine, drawn as a link
  that opens the card's authority section.
- `kg.render.authority-link-is-confirmed-or-rejected` — **[GAP]** (→ #4828, → #5123) a proposed
  link is a question on the card: the candidate's name, description and, for a place, where it
  is on a map, with Confirm and Not This One; a rejected candidate is kept so it is not offered
  again. Today the only sheet that could create a link (`EntityAuthorityLinkSheet`) is in the
  unreachable `EntityDetailView`; nothing reachable calls `linkAuthority`.
- `kg.render.enrichment-is-reachable-from-the-card` — **[PARTIAL]** (→ #4759) "Enrich from
  Wikidata…" is in the Entities table's right-click menu only
  (`EntitiesTableView.swift`, `WikidataEnrichmentSheet.swift`). Intended: also on the card.
- `kg.render.authority-places-reach-the-map` — **[GAP]** (→ #5123) a confirmed place link's
  coordinates draw the place on the map, hollow, labelled as from the authority. Today the map
  plots only coordinates on statements (`claimGeo`).
- `kg.render.authority-dates-reach-the-timeline` — **[GAP]** (→ #5123) a confirmed person
  link's life dates draw as a faint span behind that person's statements on the timeline.

### D. When and where, for more than one document

- `kg.render.timeline-and-map-for-a-name` — **[GAP]** (→ #5037) the entity card has When and
  Where sections: that name's dated statements on a small time axis and its placed statements
  on a small map, each mark opening its statement. Today both views exist only for one
  document, in the Reader.
- `kg.render.timeline-and-map-for-a-project` — **[GAP]** (→ #5037; owned by
  `explore.time.timeline-of-any-set`, `explore.place.map-of-any-set`) the Entities and Claims
  collections can be seen as a timeline and as a map.
- `kg.render.a-mark-opens-its-statement` — **[BROKEN]** (#5037, #6776) choosing a mark on the
  timeline or a pin on the map selects that statement and offers its page. Today both only
  select the statement's first entity (`KGTimelineView.handleTap`, `KGMapView` pin tap); the
  timeline picks the nearest mark by date alone, so a tap in an empty stretch still selects
  something.
- `kg.render.view-names-say-what-they-are` — **[BROKEN]** (#5037, #6776) the Graph view's help text
  names a web renderer the view no longer uses, and the Map view's help text says "a visual
  canvas" for what is a geographic map (`KGSurfaceTab.helpText`).
- `kg.render.views-are-one-click-in-the-reader` — **[PARTIAL]** (#5037, #6776) Graph, Timeline and
  Map are offered where the Reader's other views are chosen, under the same names everywhere.
  Built: the Reader's view chooser lists them (`ReaderLens`, `ReadingPaneView.readerSelector`),
  and the View menu's Add View items do too. Not the same names: the chooser says "Node Graph"
  where the menu says "Graph" (`ReaderLens.title`, `KGSurfaceTab.title`). Not checked on
  iPhone in a running app.

### E. Searching the graph

- `kg.render.search-results-group-by-kind` — **[GAP]** (→ #4604) a search shows names and
  statements as their own groups above the pages: a name row opens its card, a statement row
  opens its page with the passage lit. Today name and statement hits are folded into document
  rows, and only when that document had no text hit (`ContentView.rowHits`); a hit opens the
  document with nothing lit (`openHitDocument` takes only a document id).
- `kg.render.find-a-name-from-anywhere` — **[PARTIAL]** (#1789) from a name anywhere, "Find in
  Project" lists every page that mentions it. Built: the card's title and the Entities tab's
  context menu (`EntitySearchState`). Not built: from a lit name in the Reader text, a graph
  node, a table row.
- `kg.render.show-in-graph-shows-a-graph` — **[BROKEN]** (#5037, #6777) "Show in Graph" opens a
  graph focused on that name. Today it opens the Entities table
  (`ContentView+RootLayout.swift`, `graphRevealRequestToken`).
- `kg.render.path-between-two-names` — **[GAP]** (#5037, #6777) with two names selected, "How Are
  These Connected" draws the shortest chain of statements between them, each link opening its
  page. The engine route exists (`/api/kg/graph/path`); `kgGraphPath` has no caller.
- `kg.render.graph-has-a-find-field` — **[GAP]** (#5037, #6777) the graph has a find field that
  refocuses on a name; a focus history gives Back and Forward. Today refocus is by tapping a
  visible node only, and there is no history (`KGFocusState`).
- `kg.render.structured-query-is-for-experts` — **[OK]** the SPARQL console is its own window
  under the Project menu (`PageAndProjectMenuCommands.swift`, `SPARQLConsoleView.swift`). It is
  the expert's way, not the reader's. Tests: `fichero/Tests/Unit/general/App/MenuTerminologyBoundaryTests.swift`::testProjectMenuDeclaresTheStageSectionsInRecipeOrder.

### F. Asking, and citations in answers

- `kg.render.ask-names-what-it-does` — **[PARTIAL]** (→ #5029) "Ask" in the search field turns a
  question into a search (`runTransientSearch(compile:)`) and shows what it searched for. It
  gives pages, not an answer. Intended: the field says so, and offers "Answer from these
  pages", which opens the chat on the result set (built: `openChatWithSearchResults`).
- `kg.render.answer-cites-pages` — **[GAP]** (→ #1828, #6778) each claim in an answer carries
  a numbered citation; the Sources list under it names, for each, the document, the page and
  the quoted passage. Today `DocumentSource` holds a document id, a name, an excerpt and a
  score, with no page, segment or span, and the list shows the name and a percentage.
- `kg.render.citation-opens-the-passage` — **[GAP]** (#1828, #6778) choosing a citation opens the
  page with the passage lit in the text and on the image, through the same request a statement
  uses (`ClaimSourceNavigationRequest`). Today a source row is not a control; the Cited ledger
  (`SourcesLedgerView.swift`) is text only.
- `kg.render.score-is-not-shown-as-certainty` — **[GAP]** (#1828, #6778) a retrieval score is not
  drawn as a percentage beside a source. It reads as "how true", which it is not.

### G. Structure

- `kg.render.one-typed-path-to-the-engine` — **[PARTIAL]** (→ #4526) every call goes through the
  one client (checked: no view opens its own connection for knowledge data). But the
  knowledge-graph services send 104 hand-written paths with untyped bodies
  (`EntityService+*.swift`, `KGCurationService.swift`), and views parse metadata dictionaries
  themselves (`EntityTableRow`, `EntityStore+Authority`).
- `kg.render.graph-is-usable-without-a-pointer` — **[GAP]** (#4464, #6779) the graph's nodes and
  edges are reachable by keyboard and by VoiceOver, with a list of the same nodes as the
  fallback. Today it is one drawn canvas with tap targets and nothing else.

## Research flows (where each starts, and how many actions today)

An action is a click, a tap, a menu choice or a typed query with Return. "Target" is what this
spec asks for.

| Flow | Starts from | Today | Target |
| --- | --- | --- | --- |
| Find a person across pages | sidebar: Entities, pick the row, click the name on the card | 3 | 2 |
| | search field: type the name, Return | 1, but the person is not a result, only pages | 1, person first |
| | Reader: click the lit name, then Find in Project from the inspector's menu | 3 | 2 (menu on the name) |
| Check a statement against the page image | inspector or Claims table: click the statement | 1 (region lit only when the statement has one) | 1 |
| | graph: click the edge | 1 | 1 |
| | timeline mark or map pin | not possible | 1 |
| Confirm or reject an authority link | the card | not possible | 1 per candidate |
| Bring in authority statements | Entities table, right-click, Enrich, tick, Import | 4 or more | 2 from the card |
| See when things happened | Reader: view chooser, Timeline (one document only) | 2 | 2 in the Reader, 2 for a name or a project |
| See where things happened | Reader: view chooser, Map (one document only) | 2 | same |
| Follow a lead | graph: tap a neighbour to refocus | 1 per step, no way back | 1, with Back |
| | from a statement to the other name in it | inspector: 2 or more | 1 (the name is a link) |
| Ask a question, check the answer | search field (Ask), then chat on the results, then find the page by hand | 4 or more | 2: ask, click the citation |

## Test matrix

| Leg | What it proves |
| --- | --- |
| Engine unit | the neighbourhood answer marks each object as a name or a phrase, carries when and where on each edge, and never lists a phrase as a neighbour |
| Swift unit | `GraphSimulation.rebuild` makes no node for a phrase; a tap resolves only to entity ids; one function maps a statement to its sure-or-unsure mark for every surface |
| Swift unit | a citation and a search hit build the same source request as a statement row |
| UI (Mac, iPad, iPhone) | each flow in the table above, counted |

## Open questions

1. Is the graph's home the entity card (a small neighbourhood under the statements), a view mode
   of the Entities collection, or both? This spec assumes both; #5037 holds the ruling.
2. Events: a node by default, or off until asked for? This spec says off.
3. Should a keyword (concept) ever be a graph node? This spec says only when asked for.

## Issues filed (milestone kg-rendering)

- #6772 graph draws object phrases, dates among them, as nodes; tapping one breaks the graph.
- #6773 a statement's when and where are not carried on graph edges or drawn on sentences;
  the inline editor has no place.
- #6774 the graph has no kinds control and opens on an arbitrary entity; the document
  inspector lists Dates as a kind.
- #6775 one sure-or-unsure mark for every surface, decided by the engine; a correction is
  drawn as kept.
- #6776 timeline and map marks do not open their statement; view help text is wrong; the
  views have two sets of names.
- #6777 "Show in Graph" opens a table; no path between two names; no find or history in the
  graph.
- #6778 answer sources carry no page or passage and are not clickable; a score is drawn as a
  percentage.
- #6779 the graph is not reachable by keyboard or VoiceOver.
