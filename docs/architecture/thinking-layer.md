# The Thinking Layer — Source Outline + Workspace (Epic #1488)

> Status: **design / blueprint** (2026-06-01). Authored from a code-architect
> survey of the existing codebase. Drives the sub-issues filed under epic #1488.
> HARD RULE in force: **iterate, never replace** — every item below extends a
> component that already exists.

## The core finding

Most of this is **already modeled in code**. The thinking layer is largely a
matter of *surfacing and connecting* existing primitives, not building new ones.

| Capability | Already exists | Where |
|---|---|---|
| Workspace container | `Document.is_workspace` + `Document.curated_items` | `fichero-engine/src/fichero/models.py:209` |
| Workspace shell UI | `ResearchWorkspaceView` (CHAT\|BROWSER\|TASKS), flagged ON | `fichero/fichero/Views/Research/` |
| Project model | `ResearchProject` (+ Plan/Task/Step), `Project`/`ProjectInclusion` | `research_models.py`, `knowledge_models.py:1128` |
| Notes (Zettelkasten) | `Note` + `NoteKind` (zettel/reference/hub/inbox/fleeting/permanent), backlinks | `knowledge_models.py:1148`, `api/routes/notes.py` |
| Source notes UI | `DocumentNotesTab` (notes linked to a document) | `Views/Library/DocumentInspector/DocumentNotesTab.swift` |
| Span/page annotations | `Annotation` (doc+page+char+bbox, kinds: highlight/note/rating/bookmark/comment) | `knowledge_models.py:1236` |
| Chapter/section structure | `BookStructureNode`, `Document.structure` | `knowledge_models.py:591` |
| Spatial maps / 3D | `SpatialScene3D`, `Spatial2DCanvas`, `MindPalaceLibraryProjector` | `Views/MindPalace/` |
| Source hierarchy | `DocType` folder>group>file>page>chunk via `parent_id`; `Artifact` | `models.py` |

**The only schema gap found in the entire design:** `Note` cannot attach to a
`BookStructureNode` (chapter/section). One nullable field fixes it.

## The layered model

```
┌─────────────────────────────────────────────────────────────────────┐
│  THINKING LAYER  (Epic #1488)                                        │
│                                                                      │
│  Thing 2: WORKSPACE  (synthesis / authoring surface)                 │
│    WorkspaceFolder (is_workspace=true Document)                      │
│    ├── curated_items: [ALIASES → library docs/entities/claims/notes] │
│    ├── user Notes (NoteKind: zettel/hub/reference/permanent)         │
│    ├── ResearchProject (browser, tasks, plans) — a sub-surface       │
│    ├── Spatial views (MindPalace 2D map / 3D)                        │
│    └── Book structure (chapters > sections as outline nodes)         │
│                                                                      │
│  Thing 1: SOURCE OUTLINE  (navigation / grabbing surface)            │
│    folder > doc/group > chapter/section > page > chunk               │
│            ↓                                                          │
│            annotations / artifacts / citations / translations        │
│            entities > SVO claims > hermeneutic statements             │
│    [Select any row → "Add to Workspace" → alias into Thing 2]        │
├─────────────────────────────────────────────────────────────────────┤
│  KG / HERMENEUTICS / EMBEDDINGS LAYER                                │
│  KnowledgeEntity · KnowledgeClaim(SVO) · Annotation · Reference      │
│  HermeneuticStatement · BookStructureNode · LanceDB · search         │
├─────────────────────────────────────────────────────────────────────┤
│  SOURCE LAYER                                                        │
│  Library > Folder > Group/File > Page > Chunk  +  Artifact           │
│  DocumentCitation · SourceMetadata · provenance_chain                │
└─────────────────────────────────────────────────────────────────────┘
```

Thing 1 drills **down** through the stack and grabs pieces. Thing 2 floats **on
top** and pulls pieces up *by alias* (the library stays canonical — #1487).

## Two things, two charters

**Thing 1 — Source Outline Navigator.** One hierarchical drill-down over the
whole corpus at every granularity (folder → chapter → page → annotation →
entity → claim → citation/translation). Charter: **navigation + selection**.
Read material in context, grab items into a workspace. Source-tied notes anchor
to a document / page / span. Does not rearrange the library.

**Thing 2 — Workspace (Thinking / Authoring surface).** A named, persistent
container for synthesis: a book chapter, a thesis argument. Holds **aliases**
(not copies) of sources/entities/claims/notes + user-authored notes + an
internal structure (outline / map / 3D). Charter: **synthesis + authoring**. The
existing `ResearchProject` (web browser + tasks + agent) is a *specialized
sub-surface* that docks inside a workspace. A workspace "for a book" has a
chapter/section sub-structure where material and draft text are placed.

## Note-kinds taxonomy

| Kind | Attaches to | Model | Status |
|---|---|---|---|
| Source note | `Document` (any level) | `Note.linked_document_ids` + `kind=reference` | exists (surface `kind` on create) |
| Page/span annotation | doc+page+char+bbox | `Annotation(kind=note)` | model complete |
| Zettel | free-floating, links out | `Note(kind=zettel)` + Luhmann `address` | modeled, no browser UI |
| Hub note | indexes zettels | `Note(kind=hub)` | modeled, no UI |
| Workspace/project note | `ResearchProject` | `ResearchNote.note_type` | exists in Tasks pane |
| Outline/chapter note | `BookStructureNode` | `Note.linked_structure_node_id` | **GAP — add field** |
| Entity bio/summary | `KnowledgeEntity` | `Note.linked_entity_ids` + `kind=reference` | modeled, not surfaced |
| Marginal note | page bbox region | `Annotation(kind=note)` | modeled |
| Fleeting / inbox | quick capture | `Note(kind=fleeting/inbox)` | modeled, no capture UI |

Keep `ResearchNote` (ephemeral research tracking) and `Note` (durable KG
contribution) as distinct models — do not merge.

## Sub-issue map (filed under #1488)

Foundational backend first, then Thing 1, then Thing 2, then visibility/notes.

1. **(backend)** `Note.linked_structure_node_id` — the one schema gap.
2. **(backend)** Workspace CRUD + `curated_items` contract (`PATCH .../workspace`, resolve-aliases GET).
3. **(backend)** Source outline endpoint — aggregation over existing tables.
4. **(fe)** `SourceOutlineView` — new `InspectorTab.outline`.
5. **(fe)** Surface chapter structure in Content tab.
6. **(fe)** "Add to Workspace" picker (Thing 1 → Thing 2 bridge; alias per #1487).
7. **(fe)** Promote `ResearchWorkspaceView` → general `WorkspaceContainerView`.
8. **(fe)** Workspace curated-items pane (aliases list + go-to-source).
9. **(fe+be)** Book/chapter workspace structure (outline mode).
10. **(fe)** Workspace spatial view — reuse Mind Palace projector (ties to #1455).
11. **(fe)** Make Research/Workspace mode visible (Window menu, shortcut, tooltip, onboarding).
12. **(fe)** Standalone Notes Browser (`NotesBrowserView`).
13. **(fe)** Entity bio note in entity inspector (#1484–#1486 series).

## Open questions (need Daniel's call before building the dependent issues)

1. **Workspace == extended ResearchProject, or its own model?** (`Project`/`ProjectInclusion` already exist as an alternative.) Blueprint default: one `WorkspaceContainerView`, browser as a toggleable mode.
2. **Does a workspace appear in the main library folder tree, or only in the Workspace sidebar mode?** (`is_workspace` supports either.)
3. **"Book with chapters" — workspace sub-structure, or its own model type?** (Reuse `BookStructureNode`, or a new authoring-outline model?)
4. **Source Outline — replace the existing inspector tabs, or sit alongside?**
5. **Spatial view — a view-mode toggle inside the workspace, or a dedicated tab?** (Interacts with how #1455 resolves.)

## CONSTITUTION.md addition (proposed)

> The thinking layer sits above the archive: a **source outline navigator**
> drills through every granularity of the corpus and lets the researcher grab
> pieces into a **workspace** — a curated, alias-based synthesis surface (never a
> copy of the archive) where notes, maps, and outlines live alongside the
> gathered material, forming the bridge from reading to writing.
