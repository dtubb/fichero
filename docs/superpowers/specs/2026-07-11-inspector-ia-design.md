# Inspector Information Architecture — Design (2026-07-11)

Status: approved direction (Daniel, 2026-07-11). Supersedes the 10-tab
DocumentInspector. Canonical GitHub epic: **#3434**.

## Problem

The DocumentInspector has **10 icon-only tabs** (Content, Artifacts,
Annotations, Notes, Interpretation, Entities, Knowledge Graph, Citations,
Edits, Info) and we want to expose *more* engine capability (PyKEEN
predictions, network graph, SPARQL/RDF, richer citation/provenance). Ten
icon-only segments already exceed a comfortable native switcher; adding more
makes it worse.

The bloat comes from the Inspector trying to be three surfaces at once. There
are really three:

- **Reader** (`Views/Reader/`) — the visual canvas: PDF/text pages,
  thumbnails, loupe, annotations shown *in place*. WebKit-based. Job:
  **explore / move around / visualize** (node editor, force graph).
- **OntologyBrowser** (`Library/ViewModes/Ontology/`) — library-wide
  knowledge: entities, claims, `ForceDirectedGraphView`, duplicates,
  provenance, audit. Job: **explore + curate at library scope**.
- **DocumentInspector** — per-selection detail workspace. Job: **see, edit,
  and navigate the database for the current selection**.

## The Inspector's job (load-bearing decision)

The Inspector is the place to **edit the database** for the current
selection, and navigate from any record back to its source. It is *not* a
second Reader and *not* a visualizer.

- **Scope = the current selection: a document OR its children.** If a folder
  of PDFs is selected (and children are enabled), the Inspector aggregates
  across children — e.g. review *all* entities in a folder, then filter,
  merge, split, delete, or run duplicate prediction across them.
- **Edit, don't visualize.** Filtering, merging, splitting, deleting,
  prediction, and provenance/lineage display live here. Heavy visualization
  (force graph, image editing) stays in Reader / OntologyBrowser; the
  Inspector *links out* to them.
- **Always reach the source.** From any entity/claim/citation the user can
  jump to its source document + page + region (popover for a quick look,
  reveal-in-reader for the full context). This is a cross-cutting contract,
  not a per-tab feature.

## The 4 tabs (down from 10)

| Tab | Absorbs | Native controls | Notes |
|---|---|---|---|
| **Source** | Content, Info, Outline | `List`/text; **SwiftUI OutlineView** for document structure; **NSPathControl** for the storage-location row; "cite this document / page" export | "What the document *is*" + how it is stored. Image **Edits leaves for the Reader canvas**. |
| **Artifacts** | Artifacts (transcription, catalogue, translation, summary) | `List` + detail, lineage/provenance | Workflow-derived outputs. Translation stays an artifact, not its own tab. |
| **Knowledge** | Entities, Knowledge Graph, PyKEEN predictions, **Citations** | **OutlineView** (entity → claims → provenance is hierarchical); `Table` only for column comparison; link-out to force graph | The database editor. See the Knowledge tab section below. |
| **Notes** | Notes, Annotations, Interpretation | Shared list/detail chrome; Annotations keep source anchors | The human/THINK layer. Three sections sharing chrome, **not** a shared data model. |

**What leaves the Inspector entirely:** image **Edits** → Reader canvas
toolbar; the **visual network graph** → OntologyBrowser (Inspector links to
it).

**Switcher pattern (UNRESOLVED — decide from wireframes):** on Mac the
Inspector is a *narrow* trailing column beside the sidebar and Preview pane,
so horizontal width is scarce. A vertical side-rail (Figma-style) steals that
width and is likely wrong here. Candidates to compare: (a) compact **top icon
row** / segmented control, (b) **popup menu** switcher (most width-thrifty),
(c) side-rail (only if width allows). Constraint: with only four tabs, favour
the most width-thrifty native control that still shows all four at a glance.

## Knowledge tab (the core)

Entities and claims are the same object at two granularities: entity = node,
claim = edge. Citations are also claims — a citation-usage is "this document
says X about [cited work]" (subject = document, object = cited source, plus
provenance). So Knowledge holds:

- **Entities** — people/places/orgs/concepts across the selection. Filter,
  merge, split, delete. **Duplicate prediction** (engine merge candidates,
  #3317) surfaces likely-duplicate entities to reconcile.
- **Claims** — SVO statements with provenance. Trace each claim → source
  (popover + reveal-in-reader). Claims carry a **speaker/attribution**
  dimension: the assertor may be the **document/article itself** ("Article
  says XYZ about Z") *or* a **person in the archive** ("Person P says XYZ
  about Z"). Speaker + quotation provenance (who said it, where, verbatim
  span) is surfaced and editable — this is the speaker/quote exposure the
  engine already extracts.
- **Predictions** — PyKEEN link/ontology predictions as a review lifecycle
  (accept/reject), persisted before exposure (#3445).
- **Citations / References** — the four kinds, treated as claims/entities:
  1. citation *of* this document (how to cite it),
  2. citation of a *page* of this document,
  3. in-text citation *usages* on a page,
  4. references the document *cites* (bibliography).
  Each carries provenance and what the document asserts about it.
- **Export** is first-class: citations (and other knowledge) must **copy and
  drag-and-drop out to a citation manager** (BibTeX / RIS). SPARQL / RDF
  export is an **action**, not a permanent tab (build UI on the existing
  #3298 W3C query layer).

## Provenance → source (the core affordance)

Every claim/entity/citation carries a **source anchor**: document + page +
`bbox` region + optional verbatim span. Two-tier reveal:

1. **Popover quick-look** — hovering/clicking the source chip on a row opens a
   popover showing the *cropped source region* (the bbox rendered from the
   page image via the storage endpoint, never a local path) plus the verbatim
   span and the speaker/attribution. A glance, no navigation.
2. **Reveal in Preview pane** — a "Reveal" action drives the center **Preview
   pane** to that document/page and **highlights the region**. The user stays
   in context; the inspector selection and the preview stay in sync.

This requires the source request to carry `document + page + bbox + intent`
(preview vs reader) — today it carries neither region nor intent (#2105 is the
gap). Layout: sidebar (library) │ Preview pane (center) │ Inspector (trailing).

## Cross-cutting contracts (apply to all four tabs)

- **All transport is generated OpenAPI** — no hand-rolled `URLSession`.
- **Observable stores own fetches + mutations** — no singleton service
  lookups, no `NotificationCenter` for app state.
- **Selection / full-row / drag-drop** — native full-row selection,
  keyboard navigation, defined pasteboard semantics (#3434, #3425).
- **Per-window/library scoping** — selection + source state scoped per
  window, never a global singleton (#3437).
- **Shared action-history + undo** — every mutation routes through one
  audited command path with ⌘Z (#3444, #3302).
- **Source navigation with region** — the source request carries
  document + page + `bbox` and states preview vs reader intent (#2105).
- **Bottom filter mini-toolbar** — each tab has a bottom mini-toolbar for
  filtering/scoping the list, using standard cross-platform UX that works on
  macOS, iPadOS, and iOS (one adaptive control, or a Mac variant + an iPad
  variant where the platforms genuinely diverge).

## Missing engine exposures to surface (were hidden)

PyKEEN predictions, network/force graph (link-out), SPARQL/RDF export,
speaker/quote + temporal provenance. The engine already produces these; the
rule is **the engine exposes complete typed capability through OpenAPI
(#3442) and the UI decides what to foreground vs progressively disclose** —
the UI must never infer omitted fields from backend internals (#1768).

## Reuse beyond the document inspector

Build the shared inspector chrome as **reusable components**, not
DocumentInspector-specific ones: the switcher, list/detail split, full-row
selection, source-navigation, action-history/undo, bottom filter mini-toolbar,
and the entity Lozenge. `WorkflowInspector` (which already has its own
`InspectorTab`) and other inspector contexts should adopt the same contracts
rather than re-implementing them. Consolidation (#3454) picks the reusable
`Inspector/*Pane` tree as the survivor precisely so these components are
context-agnostic. Iterate on what exists; do not rewrite.

## Repo clean (this pass)

- Over-engineering / dead code on the inspector surface (ponytail-audit +
  `find_dead_code`).
- Duplicate transport / view-local state that should be on stores.
- Milestone/issue hygiene: retire empty folded milestones, close stale/dupe
  issues, priority-order the rest.
- Stray uncommitted edit: `OntologyBrowser+Sheets.swift` swaps in-place list
  updates for full `loadEntities()` reloads — violates the
  no-wholesale-list-rerender rule. Revert or fix.

## Build order (priority spine — P0 → P3)

Priority labels, not due dates, are the spine (dates are cosmetic buckets).

- **P0 — foundation (must land first, all tabs depend on it):** #3437
  per-window scoping, #3434 facet grouping/IA, #2105 source-nav with bbox,
  #3444 shared action-history/undo.
- **P1 — engine contracts + the Knowledge tab:** #3442 complete typed API,
  #3445 PyKEEN lifecycle, #3443 typed content representations, #3420 artifact
  lineage, entity store/merge remainder (#3185, #3186, #3300), citation
  engine contracts (#3251–#3256).
- **P2 — per-tab adoption:** Source (#3440 outline), Notes
  (#3428/#3430/#3432 store injection + dead nav bus), Artifacts (#3426),
  Citations UI (#3254/#3258 folded into Knowledge).
- **P3 — progressive disclosure + polish:** SPARQL/RDF UI (#3298), network
  graph link-out, export/drag-drop to citation managers, reconciliation
  (#3318), curation queue (#372).

## Milestone alignment

The four tabs feed from the existing milestone buckets:

- **Source** ← Content (+ Content-Engine); Outline folded in.
- **Artifacts** ← Artifacts (+ Artifacts-Engine).
- **Knowledge** ← Entities (+ Entities-Engine) + Knowledge Graph (+ KG-Engine)
  + Citations (+ Citations-Engine); Ontology folded in.
- **Notes** ← Notes + Annotations (+ Annotations-Engine) + Hermeneutics
  (+ Hermeneutics-Engine, "Interpretation").

Retire (empty / done / irrelevant): Inspector View - References,
Inspector View - Ontology, Inspector View - Outline,
Inspector View - Image Edits, Inspector View - Curation. Milestone *merges*
into exactly four are deferred as a follow-up (closed history is not worth a
destructive mass-move); the 4-tab grouping is carried by the epic + priority
labels.
