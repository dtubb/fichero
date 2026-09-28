# Explore: by meaning — what the vectors can do — Design Spec (#5030)

> Milestone: explore
> Manual: TBD — a section of "Exploring a project": finding pages like this one; seeing search
> results in groups; laying a folder out by meaning; what the groups and labels are and are
> not (a model's suggestion of what is alike, never a fact about the sources).
>
> **Status: DRAFT — first pass, 2026-09-20.** Foundation, words and common rules: `explore.md`.
> Tags as there. Slices 1, 3 and 4 cite their own issues (#5033, #5035, #5036; #5038 for the
> dependency); every other [GAP] cites #5030 (this family's issue) or the epic #5032.

## Intent (the design)

Every passage, entity and claim in a project already has a vector: a list of numbers that puts
things with similar meaning near each other. Search uses them. Nothing else does. This family
lets a researcher USE that nearness directly: "show me more like this page"; "my 195 hits fall
into four groups"; "which pages in this volume are unlike all the others?"; "lay this folder out
so that like sits by like".

Two engine pieces serve every behaviour here: **nearest neighbours of an item**, and
**group-and-label a set**. They are built once. The map is one more user of them.

Lives in: a Library listing (more like this, grouped results), and a NEW Library view mode of
its own, **Meaning**, which draws a set as points with like beside like. It is NOT an
arrangement of the Canvas or the Space (RULED 2026-09-20: those are the researcher's hand-made
spatial workspace; exploring is a different thing). An earlier note on #5030 proposed using the
two spatial views; this ruling supersedes it.

## Prior art

Nomic Atlas is the model of the result and of the ease: a zoomable map, topic labels that
change with zoom, lasso, colour by any field, duplicate detection. It is hosted, so it is a
model and never a dependency. Underwood's caution applies to every group and label: a model's
grouping is evidence to be read, not a finding. Methods adopted are the standard ones already
in the bundle's scikit-learn: PCA, t-SNE, k-means, HDBSCAN; labels from the distinguishing
keywords and entities of a group (class-based TF-IDF, the approach BERTopic made standard),
computed locally.

## What exists (detail in `agent-work/dh-layer/what-exists.md`)

Vectors for passages, entities and claims in three LanceDB tables, each stamped with its model.
A related-documents route (`GET /documents/{id}/related`) and similar-entity lookups. A search
response that says which leg found each hit. **No projection, grouping, labelling, outlier or
near-duplicate code exists, and no view mode that draws points.** scikit-learn is in the staged
bundle only as a dependency of other packages; this family must DECLARE it (#5038).

## Behaviors

More like this
- `explore.meaning.more-like-this` — **[PARTIAL]** (#5033) from any document, page or entry, one
  command lists its nearest neighbours by meaning as an ordinary Library listing, nearest first,
  each with how near it is. Built today: an engine route for whole documents only, mixing
  meaning with shared entities; no command in the app was found.
- `explore.meaning.neighbours-at-every-level` — **[GAP]** (#5033) the same command works from a
  passage, an entity and a claim, and (when the source model lands) from a segment; the answer
  lands on the passage or segment, not just its page.
- `explore.meaning.says-why` — **[GAP]** (#5033) each neighbour shows the passage that matched,
  so "like this" can be judged by reading, and says when shared entities, not meaning, put it
  there.
- `explore.meaning.same-space-only` — **[OK]** vectors from different models are never compared:
  each table is stamped with its model id and a mixed search is refused
  (`db/embeddings.py`, `assert_vector_table_model_compatible`; pinned by
  `tests/unit/db/test_embedding_drift_guard.py::test_drift_guard_detects_mixed_space_beyond_first_rows`,
  which stamps 40 rows with two model ids and asserts the refusal is raised — the guard scans the
  WHOLE model-id column, so a partial migration whose first rows agree is still caught). Every
  behaviour here inherits this.

Groups
- `explore.meaning.group-a-set` — **[GAP]** (#5035) any set can be grouped by meaning; the engine
  returns each item's group, the group's label, and the items it could not place. Items that
  belong to no group are their own honest group ("not grouped"), never forced into one.
- `explore.meaning.group-search-results` — **[GAP]** (#5035) a search result can be shown in
  headed groups in the ordinary results list, with no map at all.
- `explore.meaning.labels-from-the-text` — **[GAP]** (#5035) a group's label is made locally from
  the words and entities that distinguish it from the other groups, and is marked as a
  suggestion. A researcher can rename it; the rename belongs to the saved view, not to the
  sources.
- `explore.meaning.group-becomes-a-saved-search` — **[GAP]** (#5030) a group can be kept as a
  saved search or smart folder, through the existing saved-search action.

The map by meaning
- `explore.meaning.view-mode` — **[GAP]** (#5036) the Library offers a "Meaning" view mode for any
  set of documents, pages or entries: each item is a point, placed by a projection of its
  vector so that like sits by like. It is its own view mode, mounted from the one dispatch
  switch, with the Library's ordinary chrome. It is not the Canvas or the Space, stores no
  positions in them, and cannot be rearranged by hand: the picture is computed.
- `explore.meaning.search-results-first` — **[GAP]** (#5036) for a search result (tens to a few
  hundred items) the layout is computed on the spot, in about a second, and nothing is cached.
- `explore.meaning.points-on-one-surface` — **[GAP]** (#5036) all points are drawn on one drawing
  surface; the view never builds one view per point. A point shows its title and thumbnail on
  hover or when zoomed close.
- `explore.meaning.colour-by-any-field` — **[GAP]** (#5036) colour says a chosen field: group,
  date, hand, language, kind, or which search leg found the item (semantic, keyword, graph).
  Changing the colour moves nothing. A legend names every colour.
- `explore.meaning.labels-change-with-zoom` — **[GAP]** (#5030) group labels sit on the map; a
  wide view shows a few broad labels, a close view shows finer ones.
- `explore.meaning.lasso-is-the-ordinary-selection` — **[GAP]** (#5036) clicking a point, or
  dragging round several, selects them, and that selection is the Library's own, so the Source
  view, Reader and Inspector follow, and run-workflow, tag, export and open all work on it.
- `explore.meaning.search-within-the-map` — **[GAP]** (#5036) a search while the map is open
  highlights the hits in place and dims the rest, rather than re-making the map.
- `explore.meaning.folder-and-project-layout-is-cached` — **[GAP]** (#5030) for a folder or a
  project the layout is computed in the background, kept as a worked-out thing, and reused. The
  map says when it was made and with what, and how many items have been added since.
- `explore.meaning.new-items-do-not-reshuffle` — **[GAP]** (#5030) adding items places them into
  the existing map near their neighbours; the whole map is remade only when the researcher
  asks. (A map that reshuffles destroys the spatial memory that makes it worth having.)
- `explore.meaning.distance-is-not-a-measurement` — **[GAP]** (#5036) the view says, in plain
  words, that near means alike but that distances and the sizes of gaps are not measurements,
  and that a different method or seed gives a different picture. The seed is fixed and shown,
  so the same set and settings give the same map.
- `explore.meaning.large-sets-aggregate` — **[GAP]** (#5030) above a stated size the map draws
  density and group labels, and individual points only where zoomed in.

Finding the odd and the same
- `explore.meaning.odd-ones-out` — **[GAP]** (#5030) a set can be listed by how unlike its
  surroundings each item is. It finds blank pages, covers, inserts, misfiled items and a change
  of hand or language. A listing, not a judgement.
- `explore.meaning.near-duplicates` — **[GAP]** (#5030) a set can be listed as pairs that are
  almost the same (a letter copied twice, a page scanned twice), each pair opened side by side
  through the existing compare panes. Nothing is merged or deleted by this.
- `explore.meaning.same-name-two-people` — **[GAP]** (#5030) when the mentions of one entity fall
  into two clear groups by their contexts, the entity is OFFERED for splitting, with the two
  groups as the evidence; the reverse for merging. Never done silently; accepting is the
  existing split or merge action.
- `explore.meaning.topics-over-time` — **[GAP]** (#5030) groups counted against the sources'
  dates show when a subject appears and fades. Drawn by `time.md`'s timeline.

Methods
- `explore.meaning.methods-are-named` — **[GAP]** (#5035, #5036) projection offers PCA and t-SNE (PCA
  first, then t-SNE, the usual pairing); grouping offers k-means and HDBSCAN. Each is a named
  method with its settings shown, behind the one seam of `experiments-and-sharing.md`.
- `explore.meaning.umap-only-if-it-survives` — **[GAP]** (#5030) UMAP is offered only if it runs
  inside a build signed the way the release is signed. It needs a just-in-time compiler, which
  no entitlements file allows today. Until that test is passed it is not in the menu.
- `explore.meaning.dependency-is-declared` — **[GAP]** (#5038) scikit-learn is declared by the
  engine itself, not borrowed from another package's dependencies.

## How it is drawn (decided per kind; RULED 2026-09-20)

Listings (more like this, grouped results, odd ones out, near-duplicates) are the ordinary
native Library list.

The Meaning view mode has two honest routes:

- **Native**: points drawn on one SwiftUI drawing surface, with zoom, pan, hover and lasso
  written by hand. No extra process. Right for a search result or a folder: hundreds to a few
  thousand points. **Recommended for slice 4 (#5036).**
- **HTML in the view mode**, with a bundled WebGL scatterplot library (regl-scatterplot or
  deck.gl are the candidates), never fetched. Draws a hundred thousand points, with lasso and
  zoom-dependent labels already solved, and the same drawing serves the published page. Costs
  **about 500 MB for its WebKit process** as measured on the 16 GB M1 the app is tested on
  (#4999, #4997), plus a message bridge for selection. **Recommended for a whole-project map,
  and only if measuring the native drawing at that size shows it cannot keep up.** The rules of
  `explore.panes.html-view-mode-rules` apply: one such view alive at a time, released on leaving.

Both draw the same data from the engine (`explore.panes.one-data-shape`), so starting native
does not close the other door.

## Test matrix (legs this family touches)

Backend (neighbours, grouping, projection: deterministic for a fixed seed, evidence ids on every
point, a group for the ungrouped); pure Swift (hit-testing and lasso on the point surface; the
colour legend; aggregation above the stated size); availability (the Meaning view mode is offered
for sets that have vectors, and says so for sets that do not); MCP and CLI (neighbours, group a
set, project a set); click-around (choose a point, the Source view follows); load (a few hundred
in about a second; thousands in the background, cancellable, the machine stays useful).

## Open questions for the creative director

Not blocking: what a "point" is (a page, an entry, a passage); whether the UMAP test is worth
doing at all. Full text in `agent-work/dh-layer/questions-for-the-maintainer.md`.
