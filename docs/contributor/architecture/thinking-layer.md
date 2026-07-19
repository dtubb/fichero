(AI generated. Not reviewed.)

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
| Workspace shell UI | `ResearchWorkspaceView` (CHAT\|BROWSER\|TASKS), flagged ON | `fichero/fichero/Views/Chat/Research/` |
| Project model | `ResearchProject` (+ Plan/Task/Step), `Project`/`ProjectInclusion` | `research_models.py`, `knowledge_models.py:1128` |
| Notes (Zettelkasten) | `Note` + `NoteKind` (zettel/reference/hub/inbox/fleeting/permanent), backlinks | `knowledge_models.py:1148`, `api/routes/notes.py` |
| Source notes UI | `DocumentNotesTab` (notes linked to a document) | `Views/Inspector/Document/Notes/DocumentNotesTab.swift` |
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
│            entities > claims (SVO) > interpretations (hermeneutic)    │
│    [Select any row → "Add to Workspace" → alias into Thing 2]        │
├─────────────────────────────────────────────────────────────────────┤
│  KG / HERMENEUTICS / EMBEDDINGS LAYER                                │
│  KnowledgeEntity · KnowledgeClaim(SVO) · Annotation · Reference      │
│  Interpretation (hermeneutic) · BookStructureNode · LanceDB · search │
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
11. **(fe)** Make Chat/Research/Workspace mode visible (Window menu, shortcut, tooltip, onboarding).
12. **(fe)** Standalone Notes Browser (`NotesBrowserView`).
13. **(fe)** Entity bio note in entity inspector (#1484–#1486 series).

## Resolved decisions (Daniel, 2026-06-02)

1. **Workspace is its OWN container, NOT an extended `ResearchProject`.** `ResearchProject` is the **AI research-agent** surface (browser + tasks + agent); a workspace is a **place to store and link materials** (sources, entities, people, notes, annotations, maps). A ResearchProject may *dock inside* a workspace or stand alone — different object. Workspace = `is_workspace` Document + `curated_items` (aliases).
2. **Workspace lives in the library folder tree** as a special, movable folder — **and workspaces nest (sub-workspaces).** Also reachable via a Workspace sidebar mode. One source of truth, two doors in.
3. **`BookStructureNode` is for a *source* book being analysed, NOT the workspace's own structure.** The workspace is **not a book-writing app** — it's a **materials store**. Its internal organisation comes from the **node-class + grouping/hierarchy system** (below) and is shown via **map / table / list / generated-outline** views.
4. **Source Outline sits ALONGSIDE** the existing inspector tabs — a new additive `InspectorTab.outline`. Never replace working tabs (iterate-not-replace).
5. **Spatial is a VIEW MODE, not a destination.** A workspace (and the library) offers map/table/list/outline as switchable views. The standalone **Mind Palace concept is retired** and becomes the **2D map (SceneKit) + 3D map (RealityKit)** view modes — see #1455 / #1569.

### Workspace charter (refined)
A workspace is a **typed, nestable bag of aliases + own notes**, viewable as **map / table / list / generated-outline**, **searchable + filterable**, with **links between items**. The researcher *grabs* pieces (sources, pages, entities, people, annotations, maps — anything) into it by alias (never copies; library stays canonical, #1487) and can also add free-standing items (notes, etc.) directly. It is a place to **store and connect materials**, the bridge from reading to writing — *not* an authoring/word-processor surface.

## Node-class / prototype system (Tinderbox-style) — foundational direction (#1570)

Daniel's key insight: typing isn't just a workspace nicety — it's **how we decide that a set of pages *is* an archival container** (a chapter, a book, an archive unit). We need:

1. **A node class system** — any node carries a **class** (Person, Place, Source, Note, Map, Argument, Container, …) that confers **attributes (custom fields), default view, and allowed actions** — Tinderbox "prototype" semantics: changing the class changes what the node can do/show.
2. **Grouping** — combine nodes into a **bigger thing** (a composite/container node).
3. **Hierarchy** — lay nodes into a **nested** structure (parent/child), like folders/chapters.

**Fichero is already half-way there:** fixed types exist everywhere (`DocType`, `EntityType`, `NoteKind`) and #874 shipped a **user-extensible entity-type registry** — the prototype pattern, proven. The move is to **generalise #874 into a node-class/prototype registry** spanning all node kinds.

**Build order (decided): Phase 1 → then go broad (Phase 2).**
- **Phase 1 — workspace items only.** Add a user-definable **class/prototype** to workspace `curated_items` + workspace-authored notes. Class drives table columns, map shape/colour, and the generated outline. Reuse the #874 registry pattern. Leaves the `Document`/`KnowledgeEntity` god-nodes untouched. Provable in isolation.
- **Phase 2 — general node-class system.** Promote class/prototype + grouping + hierarchy to a first-class concept across Documents, entities, notes, pages — so "these pages form a chapter / this is an archival container" is expressed by class + grouping, not ad-hoc. Touches the god-node schema; a dedicated architectural epic.

Phase 1 ships value now and de-risks Phase 2; Phase 2 is where the archival-container grouping lives.

### North star: a UNIVERSAL node-class system (everything is a typed node)

The end-state (Daniel, 2026-06-02): **everything enters the class system** — folders, files,
PDFs, pages, chunks, entities, claims, notes, annotations, maps, workspaces, research projects.
Fichero is already structurally there: `Document` is a universal node tree
(folder→group→file→page→chunk via `parent_id`) typed by **`DocType`**; `KnowledgeEntity` by
**`EntityType`**; `Note` by **`NoteKind`**. The move is to **collapse those three fixed
typologies into ONE user-extensible class/prototype registry** — the existing enums become
*seed classes*, not hardcoded types. Then **grouping + hierarchy are one mechanism** for
"these pages = a chapter", "these files = an archival box", "these sources = a workspace", and
every view (table/map/list/outline) renders any node-set **by class**. (Phase 2 of #1570; the
god-node refactor is gated on Phase 1 proving the registry.)

### Workspace and ResearchProject are both first-class container NODES, distinguished by class

- **Workspace** = container node, class `Workspace` (curation + views).
- **ResearchProject** = container node, class `ResearchProject` (adds the browser + agent + tasks
  sub-surface). It is **not** "a thing you click at the bottom" — it's added to the **library tree**
  like a workspace: addable, movable, **nestable** (a ResearchProject can live inside a Workspace,
  or vice-versa). The bottom "Research" sidebar mode becomes a *filtered view* of
  ResearchProject-class nodes, not their only home.
- Charters stay distinct (materials store vs AI research-agent) and the **models are not merged** —
  only the "first-class node in the tree, typed by class" treatment is shared. This leans on #1570
  Phase 1: derive both from class rather than hardcoding two special container types.

## CONSTITUTION.md addition (proposed)

> The thinking layer sits above the archive: a **source outline navigator**
> drills through every granularity of the corpus and lets the researcher grab
> pieces into a **workspace** — a curated, alias-based synthesis surface (never a
> copy of the archive) where notes, maps, and outlines live alongside the
> gathered material, forming the bridge from reading to writing.
