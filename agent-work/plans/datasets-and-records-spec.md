# Structured data from historical materials — prototypes, attributes, views

Status: SPEC, not approved. Written 2026-08-12 for the sidebar-ux lane.
Owner decisions are marked **[DANIEL]**.

**Supersedes an earlier draft of this file** that proposed new `RecordType` /
`Record` models. That draft was wrong: it would have built a parallel system
beside one that already exists. Read §2 first.

---

## 1. What this is for

Fichero turns images into transcripts, transcripts into entities, entities into
claims. The missing step is the user's own structured data: a diary as dated
entries, a census as one row per person, a season of performances as one row per
performance, a book as a set of quotes. Then edit it, check it, and export it as
a spreadsheet, a website, or a book.

Today that work happens outside the app — the Marshall diaries directory holds
hand-written Python that builds IIIF manifests and entity JSON from 8,470 page
images. Those scripts are the feature request.

Two constraints shape everything:

**We cannot know the shape in advance.** Cardinality between source and row is
arbitrary — one page yields one diary entry, or ten quotes, or nothing. Ship the
mechanism, not a fixed set of shapes.

**Scale is corpus-sized.** The target is not a 365-row diary. It is looking at
an entire folder, or 100,000 files, as a timeline. Every design decision below
is constrained by that number, and it rules out several otherwise-attractive
approaches.

---

## 2. Most of the model already exists — build on it

`models/node_prototypes.py` implements Tinderbox-style prototypes today:

- A node's `prototype_key` names a `ClassificationValue` row with
  `dimension == document_prototype`.
- Prototypes form a class hierarchy through `parent_key` and carry inheritable
  `attributes`.
- `resolve_prototype_attributes(db, key)` merges the parent chain root → leaf so
  a child overrides its ancestors.
- It prefers raising over returning partial attributes on an unknown key or a
  cyclic chain.

Its own docstring calls it "the P1 keystone the folds build on" (#2591 / EPIC
#2081). `Document.attributes` is already documented as prototype-scoped node
attributes, and saved-search nodes already use it.

**So the primitive is built and unused.** What is missing is everything above
it: a way to define prototypes and their attributes from the UI, a way to see
attributes as columns, workflows that write attributes, and views that persist.

### 2.1 A row is a node

The earlier draft invented a `Record` because a row is not always a document.
That was solving the wrong problem. The right answer keeps the node model whole:

- **1:1** — a diary page *is* the diary entry. The row is the existing page node
  with a `DiaryEntry` prototype and its attributes filled.
- **1:N** — ten quotes from one page become **ten child nodes** of that page,
  each with a `Quote` prototype. They are nodes, so they nest, drag, alias,
  multi-select, appear in the sidebar, and drive Preview and Reader like
  anything else.
- **N:1** — a performance drawn from forty pages is one node whose anchors point
  at all forty.

This is why the node model is worth keeping: everything already built for nodes
applies to structured data for free, and there is no second grammar to learn or
maintain.

### 2.2 Anchors are the part Airtable cannot have

A derived node records where it came from — document, page, character span,
bounding box. Clicking a quote row jumps to the page and highlights the span.

The machinery exists: `Annotation` carries char-range, bbox, paragraph and ink
anchors; `SourceSupport` and `ProvenanceStep` carry claim provenance; OCR
geometry gives per-word boxes. **[DANIEL/worker] Determine whether a derived
node can reuse `Annotation`'s anchor shape rather than adding a third.**

### 2.3 Relationship to entities and claims

`KnowledgeClaim` is already an anchored row. Entities are rows. Records do not
replace them — a node attribute may hold a reference to an entity or a claim,
and the grid becomes the first place either can be read and corrected by a
person.

The semantic-index audit (2026-08-11, `agent-work/reviews/`) found entities,
claims, evidential dates and places are extracted and then never retrieved or
displayed. This is their missing read/write surface.

---

## 3. It is the library view, with saved views

**Not a new sidebar mode. Not a new node kind.** A folder rendered in the
library pane, with a view configuration that can be saved to the folder and
aliased.

- **Views are saved on the folder.** The mechanism shipped two days ago:
  #4575 gave folders a remembered view mode with an explicit
  "Remember View for This Folder". A saved view is that, carrying more: renderer,
  visible columns, filter, sort, group.
- **A view can be aliased.** Aliases are already a node type. An alias of a view
  is how the same folder appears twice — "1923 by date", "1923 unplaced entries"
  — without duplicating anything.
- **Views are exportable**, and exporting a view exports what you are looking at:
  its filter, its sort, its visible columns. See §6.

### 3.1 Renderers

A timeline is not a separate feature. It is the same nodes rendered against the
attribute whose role is `date`. This is what makes 100,000 files in a timeline a
view rather than a product.

| renderer | driven by |
|---|---|
| Icon / List / Table / Columns | existing, unchanged |
| **Grid** | all attributes as typed columns |
| **Cards** | `media` role for the image, `title` for the caption |
| **Timeline** | `date` role |
| **Map** | `geo` role |

Attribute roles (`title`, `date`, `geo`, `media`, `subtitle`) are declared on the
prototype and are what let a renderer know which attribute to point at.

**[DANIEL] Which renderers ship first?** Recommend Grid, then Timeline. Cards
and Map are more demo-friendly but the grid is what makes the data correct, and
the timeline is the thing you actually asked for.

---

## 4. Scale: 100,000 rows

This is the hard requirement and it invalidates the obvious implementations.

- **Server-side everything.** Filter, sort, group and paginate in SQL. Never
  load a table and filter in Python — the audit found `db.all(KnowledgeClaim)`
  per claim query (`kg/claim_search.py:78`) and `LIKE '%q%'` over every artifact
  (`db/__init__.py:2792`). Do not add a third instance.
- **Attributes must be queryable.** `Document.attributes` is a JSON dict today.
  Sorting 100,000 nodes by an attribute means either DuckDB JSON extraction with
  an index, or a promoted column per indexed attribute.
  **[DANIEL/worker] This is the central backend question — measure both on
  100k synthetic rows before choosing.**
- **The timeline at corpus scale is not a list of events.** It is a binned
  density histogram you zoom into, and the bins must be computed by the engine —
  `GROUP BY date_trunc(...)` — never by shipping 100,000 rows to Swift. Zooming
  in re-bins; only at the leaf does it become individual nodes.
- **The grid virtualizes** and requests windows.
- **Thumbnails**: a grid of 365 rows requests 365 thumbnails. Reuse the existing
  `InFlightCoalescer` single-flight path; do not add a second image path.
- **The summarize row is a SQL aggregate**, not a client count. `Empty 12 ·
  Filled 353 · Unique 41` per column is extraction QA — it is how you find the
  twelve pages the model fumbled — and at 100,000 rows it must never be computed
  client-side.

---

## 5. Workflows

### 5.1 A workflow can define a prototype

Two directions, both wanted:

- **Schema first.** Declare a prototype's attributes, aim a workflow at it. The
  attribute list becomes the extraction contract: the prompt is generated from
  it, the response validated against it, a missing required attribute is a
  reportable failure rather than a silently thin JSON blob.
- **Workflow first.** A workflow declares the prototype it emits. Running it
  creates the prototype if absent.

This answers "how does the workflow know what to generate per page": in the
first direction the schema is upstream of the extraction rather than downstream
of it.

**[DANIEL] Can a workflow *propose* a schema — "read ten pages and suggest the
attributes"?** Recommend: propose into the editor as a draft the user accepts;
never create silently.

### 5.2 Emitting nodes and attributes

Today every tool emits an artifact blob. `timeline.py` writes
`artifact_type="timeline"` as JSON with no event table, which is exactly why a
timeline cannot be queried, edited, sorted or exported today.

Requirements for a node-emitting output:

- A run against one page emits zero, one, or many nodes.
- Every emitted node carries an anchor to its source and the run id.
- **Re-running must not duplicate.** A re-run against the same scope updates or
  supersedes by run id rather than appending.
- **[DANIEL] Does a re-run overwrite a hand-edited attribute?** Recommend no —
  follow the existing rule, where `page_content_is_user_edited` already protects
  edited transcripts. User curation wins and persists.
- Partial failure is per node, not per run. A page that yields nothing says why.

---

## 6. Export

Four consumers of one declaration: grid columns, extraction contract, export
shape, and print/web template. **Exporting a view exports what you see** — its
filter, sort and visible columns, not the whole folder.

| target | shape |
|---|---|
| CSV / Sheets | flat, one file per prototype |
| 11ty / Sveltia | one Markdown file per node, YAML front-matter from attributes, body from a long-text attribute |
| Baserow / Airtable | CSV plus a field-type manifest |
| IIIF annotation list | anchored nodes become annotations on canvases — the archival-standards path, already half-built on ingest |
| RDF | beside `kg.nt`, which `knowledge/triples.py` already writes |
| PDF / book | ordered nodes through a layout template; `BookStructureNode` exists for the ordering |

**[DANIEL] Template language?** Jinja2 is already a dependency and is capable;
it is also an execution surface if templates are shared. Recommend Jinja2,
sandboxed, autoescaped, no filesystem access.

---

## 7. UX detail

### 7.1 The grid

A real database grid, not the Finder table view with more columns — Finder's
columns are a fixed vocabulary of file attributes and cannot express `weather`.

Worth taking from Baserow deliberately:

- **Typed cells that look like their type** — select as coloured chips, ratings
  as stars, media as thumbnails. Scanability is the point at corpus scale.
- **Filter, Sort, Group as toolbar verbs**, not buried in a menu.
- **The summarize row** (§4).
- **Row expansion** into a detail card.

Mac-native. No embedded Baserow or Sveltia: an embedded web CMS severs the row
from its source and breaks the pane grammar. They are export targets.

### 7.2 Attribute types

`text`, `long_text`, `number`, `date`, `select`, `multi_select`, `checkbox`,
`rating`, `url`, `geo`, `media`, `document_ref`, `entity_ref`, `claim_ref`.

- `date` must handle partial historical dates — "1923", "March 1923". Reuse
  `EvidentialDateRange`; do not invent a second date model.
- `geo` should reuse `EvidentialPlace`.
- The three `*_ref` types are what prevent a parallel, weaker relation system
  beside the KG. **Do not build link-to-table.**
- `media` holds a reference to a page image or artifact, never a copy.

**[DANIEL] Formulas in v1?** Recommend no — they imply a dependency graph and a
recalculation model.

### 7.3 Editing, provenance, and the prototype editor

- Cells edit in place; edits are curation and win over re-extraction.
- An extracted cell should be visually distinguishable from one a person
  confirmed. **[DANIEL] to rule on treatment**; `KnowledgeClaim`'s curation
  vocabulary is the model.
- Attributes are addable from the grid — a `+` column header.
- The Inspector gains a section showing the nodes derived from the selected
  page, so a person reading a diary sees its structured data without leaving the
  reader.

---

## 8. Deliberately not building

- A second relation system — entities and claims are the relations.
- An embedded web app.
- A new top-level sidebar mode, or a new node kind.
- Formulas, in v1.
- A second date model.
- **New `Record` models.** Nodes plus prototype attributes are the model.

---

## 9. Staging

**Stage 0 — read first.** `agent-work/reviews/` holds the 2026-08-11
semantic-index inventory (what is stored and never retrieved) and the views
audit. The grid mounts in the content pane, and `centerContentRouting` is
already the deepest uncapped generic in the app — a new branch there is how the
launch crashes happened. Cap it in `AnyView` as the `.library` case is.

**Stage 1 — prototypes become real.** UI to create a prototype, declare typed
attributes with roles, assign it to nodes. Surfacing `resolve_prototype_attributes`,
which exists and is unused. No new renderer yet.

**Stage 2 — the grid.** Attributes as typed columns, server-side filter/sort/
group/paginate, the summarize row, in-place editing. Prove it on 100k synthetic
rows before it meets real data.

**Stage 3 — saved views on folders, and view aliases.** Building on #4575's
per-folder view memory.

**Stage 4 — workflows write attributes and emit child nodes.** Both directions
of §5.1. The care goes into re-runs and protecting hand edits.

**Stage 5 — the timeline renderer**, engine-binned.

**Stage 6 — export.** CSV, then 11ty front-matter, then IIIF annotation lists,
then templates.

**Stage 7 — the same machinery pointed at entities, and panes side by side.**
See §11. Not a follow-on afterthought: it is where this stops being a datasets
feature and becomes the shape of the app.

Each stage is useful alone and shippable without the next.

---

## 11. Stage 7 — entities through the same lens, and multiple views at once

### 11.1 Multiple library views side by side

A grid without its source beside it is just a spreadsheet. The value is the
diary row and the page image visible together, or the timeline beside the grid
it summarises. That needs the content area to hold more than one library view.

This is already on the board as task #31, the multi-pane column design review;
this spec is a requirement feeding it, not a competing design.

**The danger is specific and known.** The views audit (2026-08-11) ranks
`centerContentRouting` (`ContentView+SidebarLayout.swift:122-247`) as the
deepest uncapped generic in the app — a three-way branch × three-case layout
switch × nested grid conditionals × four-way widescreen composition, every leaf
carrying `.frame + .simultaneousGesture + .overlay`, with no `AnyView`. Both
launch crashes this week were type-depth failures, and splitting the content
pane into N adds branches at exactly that point.

So: cap it in `AnyView` and add a declared depth bound in the first commit, not
after the first crash. `check_view_type_depth_bounds.py` already exists and
passes; extend it rather than discovering the ceiling at runtime.

### 11.2 Entities rendered through the same views

If entities are nodes with a prototype, "browse entities in a grid" is not a new
feature — it is the library view pointed at a different set of nodes. Columns,
filter, sort, group, summarize and export all come for free.

This **removes** a surface rather than adding one. The views audit found
`OntologyBrowser` — today's knowledge-graph surface — has no click path from any
sidebar row; it is reachable only by ⌘9 or the View menu, because
`pinnedGlobalNavigationRows()` was gutted and no `SidebarBrowserDestination`
case constructs it. It is already an orphan. Replacing it with a library view
over entity nodes gives entities the filtering, sorting and export they have
never had, and closes part of the semantic audit's "stored but never retrieved".

**Project engine-side, not in the client.** `KnowledgeEntity` is not a
`Document`, so entities appearing as nodes is a projection. #4186 — workflows
rendering twice in the sidebar — was caused by a client-built virtual hierarchy
diverging from the real one, and `buildWorkflowHierarchy` still exists as a
dormant re-entry point for exactly that bug. One source of truth, in the engine.

### 11.3 Generated things as nodes — and the reason is composition

Not only entities. Anything the pipeline generates — a person, a place, a quote,
an event, a timeline row, a claim — should be a node.

**The payoff is not browsing. It is dragging.** Drag a person into a workspace
because you want to pay attention to them. Drag three quotes, a place and a
date range into a workspace and that is the working set for a chapter. That is
the gesture the node model exists to make possible, and it is worth more than
any grid: it is how a scattered corpus becomes an argument.

Workspaces already exist. Aliases already exist. Multi-select and drag already
work on every node. So the cost is making generated things addressable, not
building a new mechanism.

Browsing benefits follow for free: an entity's children are the pages that
mention it, and entity attributes come from a prototype — `Person` with birth,
death, aliases — inherited like any other. Merging is already modelled
(`EntityMergeAudit`).

It is the honest conclusion of EPIC #2081's "everything is a node".

**A route that gets the drag without the ambiguity.** A projection with a
*stable id* is draggable: a workspace stores the reference (`entity:abc`), not a
copy, exactly as an alias does. So generated things can be composable before
they are resolved into real tree nodes — which defers the containment question
below without giving up the feature that motivates the whole idea.

**Open questions, and they are not small:**

- **Scale.** A corpus can hold hundreds of thousands of entities. A sidebar tree
  cannot show them, so top-level entity containers need the same treatment as
  the timeline: aggregate first, drill down. Possibly they are only ever reached
  through a view, never expanded in the sidebar.
- **What does Preview show for an entity?** Every other node type answers this.
  An entity has no page image. Its mentions? A generated summary? Nothing?
  **[DANIEL]**
- **Does an entity node's child list mean containment or reference?** A folder
  contains its children. A person does not contain the pages mentioning them.
  If both render as children, the tree's meaning becomes ambiguous — and the
  delete-parent class of bug lives exactly in that ambiguity.
- **Is an entity a node, or does a node project an entity?** The cheap version
  is a virtual projection for viewing; the deep version makes entities real
  nodes with real ids in the tree. The first is reversible, the second is not.
  Recommend starting with the projection and only promoting if it earns it.

---

## 10. Open decisions

1. JSON-attribute indexing versus promoted columns at 100k — measure both
2. Can a derived node reuse `Annotation`'s anchor shape?
3. Formulas in v1? (recommend no)
4. Template language — sandboxed Jinja2? (recommend yes)
5. Which renderers first? (recommend grid, then timeline)
6. Does a re-run overwrite a hand-edited attribute? (recommend no)
7. Visual treatment: extracted versus confirmed
8. Can a workflow propose a schema? (recommend draft-only)
9. Ship starter prototypes — diary entry, event, quote, person — as examples the
   way workflow presets ship? (recommend yes)

10. Multiple library views side by side — feeds task #31; requires the AnyView
    cap and a declared depth bound in the FIRST commit
11. Entities (and other generated things) via projection with stable ids, or
    promoted to real tree nodes? (recommend projection first — it is reversible
    and still draggable into a workspace)
12. What does Preview show for an entity, which has no page image?
13. Does a generated node's child list mean containment or reference? The
    delete-parent class of bug lives in exactly that ambiguity

---

## 12. Rulings — 2026-08-12

**Preview for a generated node = a generated summary, whose parts are
clickable and take you to the source.** This is the answer for every generated
node type, not only entities: a quote, an event, a timeline row all get a
summary with working links back to the page and span they came from. It keeps
the anchor promise (§2.2) at the pane level — a generated thing always shows its
way back to the evidence.

Note the summary is itself generated content and must not masquerade as source.
Whatever treatment marks an extracted cell (Q7) should mark this too.

**Prototypes are per-library, with global ones like global workflows.** A
`DiaryEntry` defined in one library stays there; a set of shared prototypes
lives globally and is available everywhere.

The mechanism for this already exists and needs no new concept:
`resolve_prototype_attributes` walks a `parent_key` chain merging root → leaf.
A library-local prototype can name a global prototype as its parent and override
selected attributes — exactly the Tinderbox inheritance the module was built
for. So "global with local overrides" is the existing resolver pointed at the
global library, not a second storage path.

**[worker] Confirm where global prototypes live** — the global library
(`global.fichero`) already holds cross-library state and is the obvious home,
but verify rather than assume, and check what happens to a library whose parent
prototype is missing because the global library is unavailable. The resolver
prefers raising over partial attributes, which is right, but a library that
cannot open because a global parent is absent would be a bad failure mode.
