# Panes, Magnifiers & Workspaces — Design Spec

> Design-led (Testing Constitution). The Fichero creative director owns this intent;
> tests enforce it; code makes them pass. One line per behavior, each to be cited by its
> pinning test. **Status: DRAFT — captured from a creative-director brainstorm 2026-09-12;
> awaiting the design lead's approval and answers to the open questions before tests/code.**
> Tags: **[OK]** today · **[BROKEN]** regression, code contradicts the line · **[GAP]**
> intended, never built.
>
> This is an AREA spec for how a window is *composed* — the pane system that hosts every
> view mode (source/preview, transcription/words, entities, claims, graph/canvas,
> inspector). It sits above the per-mode specs (`kg-tables`, `kg-entity-inspector`,
> `segment-representations`) and owns the cross-pane concerns: split, per-pane
> configuration, synchronized magnification, and saving a composition as a workspace.

## Intent (the design)

A window is a composition of **panes**, not a fixed source/detail pair. Each pane holds one
view of the library — the page image, its transcribed words, the entities, the claims, a
graph/canvas of related things, or an inspector — and each pane is **independently
configurable**: its own view mode, its own zoom, its own magnifier state. Panes compose
freely: three panes side by side, with the image shown in one and hidden in another; a
source pane beside an entity pane beside a claims pane; or two source/preview panes for
comparison. A composition can be **saved as a workspace** and reopened.

The reading surface is built for close looking. A page's original image sits in one pane;
its transcribed **words** sit in another and, on request, **expand to fill their bounding
box** so the text occupies the same geometry as the ink. A **magnifier** (a zoom bar along
the bottom of a pane) can **follow the mouse**, and magnification can be **synchronized
across panes** so moving the loupe over the original moves it over the words too — or
decoupled, one pane's magnifier open while another's is closed.

Entities and claims are not two bespoke screens; they are **two views in the one pane
system**, sharing its selection grammar, split behavior, and workspace persistence. From an
entity you can reach every source page it appears on; from a claim you can reach its
sources. Selecting related things across panes composes a working set — related entities in
a graph pane, their source pages in a preview pane, an inspector on the right — that is
itself saveable.

## Behaviors (each → one pinning test)

### A. Pane composition & split

- `panes.split.focused-column-only` — **[BROKEN]** splitting a pane (vertical or
  horizontal) splits the **focused** pane, not every column at once. Today a vertical split
  applies to both columns rather than the one selected.
- `panes.split.independent-mode-per-pane` — **[BROKEN]** each pane holds its own view mode;
  changing one pane to Entities or Claims does not clear or convert the others. Today
  switching a pane's node-type to entity/claim in the entities view removes them from the
  other panes.
- `panes.open-view-arbitrarily` — **[GAP]** any pane can be set to any view mode (source /
  words / entities / claims / graph / inspector) directly, without routing through a
  document selection. Today there is no way to open an entity or claim view arbitrarily in
  a window.
- `panes.compose-three-plus` — **[GAP]** a window supports three or more panes, and any
  pane may hide its image while another shows it.

### B. Magnifier & synchronized zoom

- `panes.magnifier.follow-mouse` — **[GAP]** a pane's bottom magnifier bar can track the
  pointer, magnifying the region under the mouse.
- `panes.magnifier.per-pane-open-state` — **[GAP]** each pane's magnifier opens and closes
  independently — one pane magnified while another is not.
- `panes.zoom.sync-across-panes` — **[GAP]** when synchronization is on, zoom/magnification
  in one pane drives the corresponding region in the others (original ↔ words), so the loupe
  is shared; sync is toggleable, off by default.
- `panes.words.fill-bounding-box` — **[GAP]** on request, transcribed words expand to fill
  their segment's bounding box, occupying the same geometry as the underlying ink (ties
  `segment-representations` — the `text` representation rendered into the segment anchor).

### C. Unified entity ↔ claims view system

- `panes.kg.one-view-system` — **[BROKEN]** the entities view and the claims view are the
  same pane-system view, sharing selection grammar, split, magnifier, and workspace
  persistence. Today they are separate implementations that behave differently.
- `panes.kg.library-change-resets` — **[BROKEN]** switching the active library resets the
  claims (and entities) panes to the new library's data. Today the claims pane does not
  reset on a library change.
- `panes.entity.sources-pane` — **[GAP]** an entity pane can show **all source pages** the
  entity appears on — scroll through them, see the same name across four documents, judge
  whether it is one person. (An entity is a name; its statements/sources are where it
  lives — see `kg-entity-inspector`.)
- `panes.claim.sources-pane` — **[GAP]** a claim (or a page's set of claims) can show its
  source pages in a preview pane, each anchored to the passage.

### D. Workspaces

- `panes.workspace.save` — **[GAP]** a pane composition (which panes, their modes, split,
  sync, and current selection scope) is saveable as a named workspace.
- `panes.workspace.reopen` — **[GAP]** reopening a workspace restores its panes, modes, and
  layout. (Ties the related-entities → sources → inspector composition in the Intent.)

## Known bugs to fix (already observed by the creative director)

1. **Split affects both columns** (`panes.split.focused-column-only`) — split should act on
   the focused pane only.
2. **Changing a pane to entity/claim wipes the others** (`panes.split.independent-mode-per-pane`).
3. **No arbitrary way to open an entity/claim view in a window** (`panes.open-view-arbitrarily`).
4. **Claims don't reset on library change** (`panes.kg.library-change-resets`).

These four are the first wave to pin — they are regressions/gaps in behavior that already
half-works, so each needs a pinning test that asserts the *behavior* (not the code) and a
fix that makes it pass.

## Open questions (for the design lead)

- **Naming.** What do we call editing directly inline within a pane, where each pane may
  carry different settings? ("inline edit mode" / "live edit" / something else?)
- **Richer subject types.** Claims today anchor people / places / organizations (and the
  model already has event / concept / citation / other). Should the claims tables and
  subject pickers surface the full set — and are there types beyond the current enum the
  creative director wants (objects, works, dates-as-subjects)? (Ties `kg-interactions`
  claim-richness.)
- **Sync granularity.** Is magnifier sync a per-window toggle, a per-pair binding, or a
  per-pane opt-in?
- **Workspace scope.** Does a saved workspace capture a live selection (these four people)
  or only the pane layout, rehydrating selection from context?

## Cross-references

- `kg-entity-inspector.md` — the entity pane's statements → source model.
- `kg-tables.md` / `kg-interactions.md` — the entities/claims tables this view system hosts;
  claim richness and the shared interaction verb set.
- `segment-representations.md` — the words/transcription representation that
  `panes.words.fill-bounding-box` renders into segment geometry.
