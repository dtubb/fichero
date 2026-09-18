# Write Layer — Design Spec (#2108)

> Milestone: write-layer
> Manual: TBD — nothing user-facing exists yet to document; a Getting Started section on
> turning notes into a draft is written once the composition surface ships.
>
> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval.** Written because six open issues
> (#2108–#2113) sat in the legacy-milestone triage queue with no spec anchor and don't fit any
> existing surface spec's scope; this is that anchor, written against the code on disk, not the
> issue bodies' own framing.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, partly proven or partly wired ·
> **[GAP]** intended, never built (needs an issue) · **[BROKEN]** regression, code
> contradicts the rule (needs an issue).

## Intent (the design)

Fichero's research lifecycle has three layers: READ (hermeneutic — decompose a source into
claims/entities/citations, KG-owned), THINK (interpretative — notes and annotations on a
reading, human + AI), and WRITE (synthesis — this spec). The WRITE layer is where a researcher
turns source-tied notes into an argument and the argument into a document: atomic notes
networked into a personal knowledge graph (Zettelkasten), an outliner to structure the
argument, a composition surface to draft prose around cited fragments, and a compile/export
step that resolves citations into a real bibliography.

**Said plainly: this cluster is mostly UNBUILT.** One piece — atomic notes with bidirectional
links and backlinks — is genuinely built and tested on both the engine and the app. Everything
downstream of it (an outliner over a draft, a composition/binder surface, drag-a-fragment-into-
draft, and compile/export with resolved citations) does not exist in the code today. This spec
stays short rather than inventing behaviors the code doesn't have.

## What already exists (grounded, read on disk 2026-09-18)

- `fichero_server.api.routes.document.notes` — the Zettelkasten Notes API (`Note`, `NoteLink`
  models in `models/knowledge.py`): full CRUD, bidirectional links between two notes
  (`POST/DELETE /api/notes/{id}/links[/{link_id}]`), and backlink/forward-link queries
  (`GET /api/notes/{id}/backlinks`, `.../forward-links`). A `Note` can reference other notes,
  entities, claims, and documents — provenance is a field on the note, not a separate join a
  UI has to reconstruct.
- Swift `NoteStore`/`NoteService` — `links(for noteId:)` wraps both backlink and forward-link
  calls into one `NoteLinks` struct; consumed by `NoteDetailView` and `NotesInspectorPane`
  (both under `Views/Inspector/Notes/`).
- **Not found anywhere in the app or engine:** a composition/binder surface, a workspace-draft
  outliner, a "drag this claim/quote/annotation into the draft" affordance, or a compile/export
  path that resolves in-text citations into a bibliography from a workspace's notes.
  `SourceOutlineView` exists but is a document's own heading/TOC outline, not a draft-structure
  outliner — a different capability with a similar name, not a partial version of this one.
  Citation EXPORT exists (`CitationExportButton`, `EntityService+Bibliography.swift`,
  `export_service.py`) but exports the KG's citation graph, not a compiled workspace draft.

## Behaviors

- `write.zettel-notes-crud` — **[OK]** a note is created, read, updated (patch), and deleted
  through one typed API; scoped to a page, a folder, or neither (a free-floating note), never
  both a page and a folder at once. Pinned:
  `test_routes_notes.py::TestNotesCRUD::test_create_get_patch_delete_note`,
  `::test_list_notes_filters`, `::test_linked_structure_node_id_create_patch_and_filter`,
  `::test_page_scoped_note_create_list_and_delete`,
  `::test_folder_scoped_note_create_list_and_delete`.
- `write.zettel-notes-linked-with-backlinks` — **[OK]** two notes link bidirectionally
  (`NoteLink`, typed `link_type`: follows/references/contradicts/supports/free), a note cannot
  link to itself, and both directions are queryable (`backlinks` = who points here,
  `forward-links` = who this note points to) — "the graph IS the analysis," per the route's own
  description. Reachable app-side via `NoteStore.links(for:)`, rendered in `NoteDetailView`/
  `NotesInspectorPane`. Pinned: `test_routes_notes.py::TestNoteLinks::test_create_and_delete_link`,
  `::test_backlinks_and_forward_links`, `::test_rejects_self_link`.
- `write.zettel-notes-are-library-nodes` — **[GAP]** (#2110) a Zettelkasten note is a floating
  object today — reachable only from an Inspector pane bound to whatever document/folder is
  selected — not a first-class node in the library/sidebar tree the way a document or a
  workspace is. #2110's own title asks for notes "as nodes"; the CRUD and linking underneath
  are there (above), the node-model integration is not. Not built.
- `write.composition-surface` — **[GAP]** (#2109, #2108) a Scrivener-like binder that holds
  source-tied fragments (notes, quotes, claims) and lets a researcher drag them into a draft,
  writing prose around them (markdown or rich text). #2109 is the keystone sub-issue of the
  parent EPIC #2108 (the whole WRITE-layer cluster this spec anchors) — both kept open, cited
  together since building this surface is what the EPIC itself is waiting on. No binder, no
  draft container, no fragment-arrangement UI exists anywhere in the app. Not built.
- `write.outliner-over-draft` — **[GAP]** (#2111) drag-reorder structure over a workspace
  draft, distinct from `SourceOutlineView`'s per-document heading outline (a different,
  already-built capability that this spec does not claim credit for). Not built.
- `write.drag-fragment-into-draft` — **[GAP]** (#2113) dragging a claim, quote, or annotation
  from the hermeneutic (READ) or interpretative (THINK) layers into a draft as a cited
  fragment — the concrete mechanism `write.composition-surface` needs to receive material from
  the rest of the app. Not built; blocked on `write.composition-surface` existing to drop into.
- `write.compile-export-with-citations` — **[GAP]** (#2112) compiling a workspace's draft to
  Word/PDF/Excel with in-text citations resolved against a real bibliography (BibTeX/CSL,
  style-selectable). Distinct from the KG's own citation export
  (`CitationExportButton`/`export_service.py`), which exports the citation GRAPH, not a
  compiled document. Not built; blocked on `write.composition-surface` existing to compile
  FROM.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | note CRUD, links, backlinks/forward-links | `fichero-server/tests/unit/api/test_routes_notes.py` |
| Backend (pytest) | n | no compile/export-with-citations endpoint exists to test | — |
| Availability (Swift) | y | `NoteStore.links(for:)` reaches both link directions | `NoteService.swift`, consumed by `NoteDetailView`/`NotesInspectorPane` |
| Availability (Swift) | n | no composition surface, outliner, or drag-fragment affordance exists | — |
| Click-around (XCUITest) | n | no dedicated flow test found (nothing to click around yet) | — |

Hard-gate: none — DRAFT spec, mostly unbuilt; a hard-gate set is chosen once the composition
surface (the keystone sub-issue, #2109) has an owner.

## Issues needing maintainer triage

None of #2108–#2113 look reshaped by a more recent ruling — read against the code, they
describe a genuinely unbuilt cluster, not a stale description of something already decided
differently elsewhere. No triage flag raised here.

## Related, not this spec

- `ui/research.md` owns the research WORKSPACE itself (a folder node, `workspace_kind=agent`) —
  the container this spec's composition surface would live inside, once built. Not restated
  here.
- `kg/kg-entity-inspector.md`'s `kg.entity.notes` behavior (currently [GAP], → #4828) covers a
  DIFFERENT notes surface — notes attached to a KG entity from the retired KG browser — not the
  general Zettelkasten notes API this spec covers.
