# Explore: networks — people and other things joined — Design Spec (#5032)

> Milestone: explore
> Manual: TBD — a section of "Exploring a project": a person's network; what an edge is and
> what it was built from; the confidence and "who says so" controls; the network "as of" a
> year; sending a network to Gephi.
>
> **Status: DRAFT — first pass, 2026-09-20.** Foundation, words and common rules: `explore.md`.

## Intent (the design)

The knowledge graph is already a prosopography: people, places, organisations and events joined
by claims that carry dates, confidence and sources. This family lets a researcher SEE it as a
network: who is tied to whom, how strongly, on what evidence, and **as of when**. Two lessons
from the references shape it. From Six Degrees of Francis Bacon: a relationship inferred from
texts is shown as inferred, and the confidence threshold is a control the researcher slides.
From nodegoat: every relation has dates, so a network without a date is a fiction; it is always
"as of".

The cheapest honest route comes first: **export the network and open it in Gephi or Retina.**
That costs an exporter and no new renderer, and it is slice 2 of the build order. Drawing inside
the app comes after, for the sizes a researcher actually reads: a person's neighbourhood, a
folder, a diary year.

Lives in: the native graph (`Views/Library/ViewModes/Graph/Ontology/ForceDirectedGraphView.swift`)
promoted from the Reader to a Library view mode for entities and claims, and kept as a Reader
rendition for one document or one entity. The engine's graph routes
(`api/routes/kg/graph.py`, on networkx) supply the analysis.

## Prior art

CBDB (structured associations, export to Gephi, Pajek and GIS), Six Degrees of Francis Bacon
(confidence as a control; scholars correct the inference), nodegoat (time-aware traversal),
Gephi's GEXF (which has native support for nodes and edges that exist only between dates) and
GraphML, Retina for sharing, sigma.js and graphology if a web drawing is ever needed. The
factoid model already used by the knowledge graph is what makes an edge resolvable to its
sources.

## What exists

- A native force-directed graph: entities as nodes, claim co-occurrence as edges, a neighbour
  limit of 30, zoom and pan, selection drives knowledge-graph focus. Reader tab only, one
  document. No time, no confidence control, no statement of what an edge is built from.
- Engine analysis with no app surface: centrality, PageRank, communities, components,
  triangles, clustering, paths, traversal, neighbourhood, structural similarity; link
  prediction (pykeen). None takes a time argument.
- Claims carry dates, confidence, `created_by` and a source anchor. `created_by` is not yet
  truthful for machine claims (→ #4868, → #4869).
- RDF export (Turtle, JSON-LD) and a SPARQL console exist. **No GEXF or GraphML exporter.**

## Behaviors

What a network is
- `explore.network.edge-rule-is-named` — **[GAP]** (#5032) a network is always made by a named
  rule, shown on the view: joined by a claim of chosen kinds; named in the same entry; in the
  same place on the same day. The same people give a different network under each.
- `explore.network.edge-opens-its-evidence` — **[GAP]** (#5032) choosing an edge selects the
  claims and passages it was built from; choosing a node selects the entity. The Source view,
  Reader and Inspector follow.
- `explore.network.edge-weight-is-a-count-of-evidence` — **[GAP]** (#5032) an edge's thickness
  says how much evidence stands behind it, and its drawing (solid, dashed) whether any of that
  evidence is stated in a source or all of it is inferred.
- `explore.network.of-any-set` — **[PARTIAL]** (#5032) a network can be asked for on one entity
  (its neighbourhood, to a chosen depth), a folder, a search result, or a collection of
  entities or claims, as a Library view mode. Built only for one document's entities, as a
  Reader tab.
- `explore.network.kinds-of-node` — **[GAP]** (#5032) people only, or people with places,
  organisations and events, is a control; node colour says kind (the existing entity-kind
  palette), node size a chosen measure.

Inferred, and who says so
- `explore.network.confidence-is-a-control` — **[GAP]** (#5032, depends on → #4868, → #4869) a
  minimum-confidence control adds and removes edges as it moves; a second control filters by
  who asserted the evidence (a person, a model, a rule).
- `explore.network.predicted-links-are-suggestions` — **[GAP]** (#5032) links the engine
  predicts (pykeen, structural similarity) can be shown, off by default, drawn unlike
  everything else, labelled with their method, and never counted as evidence. Accepting one is
  the existing create-claim action, by a person, with the person as its asserter.
- `explore.network.curation-in-place` — **[GAP]** (#5032) from an edge or a node a researcher can
  reach the existing actions (confirm or reject a claim, merge or split an entity). The network
  adds no editing of its own.

As of
- `explore.network.as-of` — **[GAP]** (#5032) the network obeys the shared "as of" control: an
  edge is drawn only while its evidence says the relation held; an edge whose dates are
  uncertain is drawn as uncertain inside its possible span; an undated edge is drawn only when
  "include undated" is on, and the count of undated edges is always shown.
- `explore.network.engine-routes-take-a-time` — **[GAP]** (#5032) the engine's neighbourhood,
  centrality and community routes accept an "as of" window, so that "who was central in 1926"
  is a real question, not a filter applied after the fact.
- `explore.network.layout-stays-put-through-time` — **[GAP]** (#5032) while "as of" moves or
  plays, nodes keep their places; edges and nodes appear and fade. A layout that reshuffles on
  every tick cannot be read.

Reading a network
- `explore.network.measures-are-named` — **[GAP]** (#5032) sizing or ranking by a measure
  (degree, betweenness, PageRank) names the measure and links to a plain-words note on what it
  does and does not mean. Communities are offered as a colour, marked as a method's suggestion.
- `explore.network.as-a-table` — **[GAP]** (#5032) the same network is always available as two
  tables (nodes, edges) with the same selection; this is also its accessible form.
- `explore.network.large-networks-aggregate` — **[GAP]** (#5032) above a stated size the view
  draws communities as single marks that open, and offers "export and open in Gephi" rather
  than a hairball.
- `explore.network.layout-is-a-method` — **[GAP]** (#5032) the layout (force-directed,
  circular, by community) is a named method with a fixed, shown seed, so the same set and
  settings give the same picture.

Out
- `explore.network.gexf-and-graphml-out` — **[GAP]** (#5034) the network of any set leaves as
  GEXF (with the dates on nodes and edges, which GEXF supports natively) and as GraphML. Every
  node and edge carries its kind, dates, confidence, asserter, the rule that made it, and the
  citable references of its evidence. Rights are applied.
- `explore.network.export-is-the-first-slice` — **[GAP]** (#5034) the exporter ships BEFORE any
  new network drawing, so that Gephi and Retina are usable at once.
- `explore.network.rdf-out-carries-authorship` — **[PARTIAL]** (#5032) the existing RDF export
  is the linked-open-data form of the same network. It is built; claim authorship is absent
  from it today (`export/exporter.md`'s design note), which publishing needs.

## How it is drawn

Native, growing the existing force-directed view. A WebGL drawing (sigma.js and graphology,
bundled) is held in reserve for a whole-project network, only if measuring shows the native view
cannot serve it as aggregates, and only after the export route has been tried in practice.

## Test matrix (legs this family touches)

Backend (each edge rule; every edge has evidence ids; "as of" on the graph routes; GEXF and
GraphML open in a standard parser; fixed seed gives a fixed layout); pure Swift (edge drawing
rule; nodes keep their places through time); MCP and CLI (export; neighbourhood as of);
click-around (choose an edge, the Source view shows a passage); load (a project's network
aggregates, the machine stays useful).

## Open questions for the creative director

Question 11 (the default edge rule). Full text in
`agent-work/dh-layer/questions-for-the-maintainer.md`.
