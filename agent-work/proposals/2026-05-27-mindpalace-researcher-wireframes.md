# Mind Palace + Researcher — Wireframes & Design

**Date:** 2026-05-27
**Lane:** opus (design only — no feature code)
**Status:** DRAFT for Daniel's sign-off. Phase-1 read-only Mind Palace code exists on
`opus` (commit `b620a829`) as reference but **will not merge** until this design is approved.
**Backend:** COMPLETE for both (`/api/mind-palace`, `/api/research`); generated Swift
typed-client already exposes them. This is a frontend-shape decision, not enablement.
**Related:** MCP #1269 (AI needs an interface to arrange the palace),
`agent-work/proposals/2026-05-27-feature-enablement-researcher-mindpalace.md` (inventory),
memory `feedback_kg_logic_in_backend`, `feedback_swiftui_splits`.

---

## Part 1 — MIND PALACE

### The vision (Daniel)

A **3D visual space** built on **RealityKit**, with a future goal of **streaming to
Vision Pro**. Archival materials are shown in 3D — documents stood up, laid out, grouped,
layered. Crucially the palace is **two things at once**:

1. **A human surface** — the researcher arranges what they're looking at, spatially.
2. **An AI surface** — the AI *manipulates* the palace (moves nodes, groups, layers, zooms,
   re-arranges) and "thinks visually" about a catalogue as both **content** and **spatial
   arrangement**. This is the #1269 MCP hook: the AI drives the same `/api/mind-palace`
   endpoints a human drag would.

It operates at **multiple levels**:

- **Library structure** — databases / folders / collections / smart-groups (the existing
  hierarchy).
- **Workspace "rooms"** — a layer **separate from the library hierarchy**. A room is a
  curated layout of whatever the user (or AI) is currently looking at. Deleting a node from
  a room never deletes the underlying document; a room is a *view*, not a container.

> **Design principle (carry everywhere):** positions, grouping, layering, arrangement, and
> camera are **backend state** (`SpatialNode.position_x/y/z`, `SpatialConnection`,
> `SpatialViewport`, `SpatialStack`, `ArrangementType`). The Swift view **renders and
> persists** — it never computes layout. This is exactly what lets the **AI and the human
> share one source of truth**: both write positions to the backend, both read the same scene.

### Backend already provides (`spatial_models.py` + `/api/mind-palace`)

| Concept | Model | Endpoints |
|---|---|---|
| Room | `SpatialRoom` (room_type: research/synthesis/presentation) | `POST/GET /rooms`, `GET/PATCH/DELETE /rooms/{id}`, `GET /rooms/{id}/scene` |
| Node | `SpatialNode` (position_x/y/z, rotation_x/y/z, scale, node_type, source_id) | `POST /nodes` (place), `GET /nodes?room_id=`, `PATCH /nodes/{id}` (move), `DELETE /nodes/{id}` |
| Connection | `SpatialConnection` (typed: evidentiary/semantic/ontological/hermeneutic/user_drawn + link_subtype) | `POST /connections`, `GET /connections?room_id=`, `DELETE /connections/{id}` |
| Stack (group/layer) | `SpatialStack` | `POST /stacks`, `GET /stacks?room_id=`, `GET /stacks/{id}`, `POST/DELETE /stacks/{id}/nodes/{node_id}` |
| Note | `NativeNote` (linked_claim/source/entity) | `POST /notes`, `GET /notes`, `GET/PATCH/DELETE /notes/{id}` |
| Camera | `SpatialViewport` (camera_x/y/z, zoom, focus_node, bookmark) | `GET/POST /rooms/{id}/viewport/{user_id}` |
| AI arrangement | `ArrangementType` (semantic/chronological/thematic) | `POST /rooms/{id}/suggest-arrangement`, `POST /rooms/{id}/focus`, `POST /rooms/{id}/capture` |
| Tinderbox I/O | — | `POST /import/tinderbox`, `POST /export/tinderbox` |

**Key takeaway:** there is already a `suggest-arrangement` endpoint and a `focus` endpoint —
the backend anticipates an agent re-arranging the room. The MCP server (#1269) wraps these
same routes so the AI's "move this group, zoom there" maps 1:1 to `move_node` /
`save_viewport` / `suggest-arrangement`.

---

### Wireframe A1 — Sidebar mode + main-view canvas (RECOMMENDED first mock)

Mind Palace becomes a **sidebar mode** (peer to Library/Search/Workflows). The sidebar lists
**rooms**; the main view hosts the 3D/2D canvas. Matches Daniel's "sidebar entry first, 3D
canvas in the main view."

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│  ◳  Fichero — Mind Palace                                          [⊟ Inspector] [↗] │
├──────────────┬─────────────────────────────────────────────────────┬─────────────────┤
│ [📁][🔍][⚡][🧊]│  Room: "LFH Catalogue"   ◇ Arrange ▾   ⊕ ⊖ ⟲ Fit   │  INSPECTOR      │
│  ▲ mode bar  │ ┌─────────────────────────────────────────────────┐ │ ┌─────────────┐ │
│              │ │                                                   │ │ │ Node        │ │
│ ROOMS      ⊕ │ │      ╭───────╮            ╭───────╮               │ │ │ ─────────── │ │
│ ● LFH Catalog│ │      │ 📄 Deed│───────────│ 📄 Map │               │ │ │ Deed 1873   │ │
│ ○ Mining hx  │ │      ╰───────╯  evidentiary╰───────╯               │ │ │ type: source│ │
│ ○ People     │ │          │                    │ semantic          │ │ │ room x/y/z  │ │
│ ○ Synthesis  │ │      ╭───────╮            ╭────┴───╮               │ │ │             │ │
│              │ │      │👤 Person│ ─ ─ ─ ─ ─│ ✎ Note │               │ │ │ [Open source│ │
│ ─ STACKS ─   │ │      ╰───────╯ hermeneutic╰────────╯               │ │ │  document →]│ │
│ ▸ Land docs  │ │                                                   │ │ │ [Reveal in  │ │
│ ▸ 1870s      │ │   ╭ stack: "Land docs" ╮                          │ │ │  Library]   │ │
│              │ │   │ ▢▢▢ (3 layered)     │                          │ │ └─────────────┘ │
│ ─ VIEW ─     │ │   ╰─────────────────────╯                         │ │  Connections    │
│ ◉ 3D  ○ 2D   │ └─────────────────────────────────────────────────┘ │  • → Map (sem.) │
│ Camera: saved│  ● 12 nodes · 7 connections · 2 stacks   [⤓ Tinderbox]│  • ← Person(her)│
└──────────────┴─────────────────────────────────────────────────────┴─────────────────┘
```

- **Sidebar (left):** mode bar adds a 🧊 Mind Palace icon; below it a **Rooms** list (CRUD via
  `GET/POST /rooms`), a **Stacks** disclosure (`GET /stacks?room_id=`), and a **3D/2D toggle**.
- **Canvas (center):** RealityKit (3D) or a 2D projection. Nodes from `GET /nodes?room_id=`,
  edges from `GET /connections?room_id=`, camera from `GET /viewport`. Toolbar: zoom/fit
  (writes `save_viewport`), **Arrange ▾** (calls `suggest-arrangement` with
  semantic/chronological/thematic), Tinderbox export.
- **Inspector (right):** selecting a node shows its metadata **and the always-present
  get-back-to-source affordance** — `[Open source document →]` (resolves `source_id` →
  the real `Document`, opens it in the reading surface) and `[Reveal in Library]`.

**Pros:** consistent with the app's primary navigation; inspector is already the home for
"details + actions"; one window. **Cons:** a full new `SidebarMode` case touches ContentView's
exhaustive mode switches; RealityKit in the main split needs care with the existing toolbar.

---

### Wireframe A2 — Separate window (the Phase-1 prototype shape)

A dedicated **"Mind Palace" window** (what the reference commit `b620a829` does today). Opened
from a gated View-menu command; the main app window is untouched.

```
   Main window (Library)                    Mind Palace window  (⌘-opened)
┌───────────────────────────┐         ┌──────────────────────────────────────────────┐
│ [📁][🔍][⚡]  Library      │         │  Mind Palace — "LFH Catalogue"      ◇Arrange▾ │
│  …documents…              │         ├───────────┬──────────────────────────────────┤
│                           │         │ ROOMS   ⊕ │   ╭──────╮       ╭──────╮         │
│                           │         │ ● LFH     │   │📄 Deed│───────│📄 Map│         │
│                           │  ◀─────▶│ ○ Mining  │   ╰──────╯       ╰──────╯         │
│                           │ "Open   │ ○ People  │        ╲ evidentiary               │
│                           │  source"│           │      ╭──┴───╮                      │
│                           │  jumps  │ 3D ◉ 2D ○ │      │✎ Note │  [Open source →]    │
│                           │  back   │           │      ╰───────╯  (focuses main win) │
└───────────────────────────┘         └───────────┴──────────────────────────────────┘
```

- Self-contained: `Window("Mind Palace", id:"mind-palace")`, gated by `isMindPalaceEnabled`.
- "Open source document →" calls `openWindow(id:"main")` / focuses the library window and
  selects the resolved `Document` — the **get-back-to-source** crossing windows.

**Pros:** zero blast radius on ContentView; natural home for an immersive/Vision-Pro surface
later (a window → an `ImmersiveSpace`); easy to make full-screen. **Cons:** two windows to
reconcile; "back to source" is a cross-window jump (focus + select), which needs explicit
plumbing; inspector duplicated or omitted.

---

### Wireframe A3 — Sidebar mode, canvas + bottom "AI arrangement" rail (shows the AI surface)

Same as A1 but makes the **AI-manipulation** explicit: a rail showing what the AI is doing /
proposing, so the human can watch or accept the AI's arrangement.

```
├──────────────┬─────────────────────────────────────────────────────┬─────────────────┤
│ ROOMS      ⊕ │  Room "LFH" — 3D            ◇ Arrange: [Semantic ▾]   │ INSPECTOR       │
│ ● LFH        │ ┌─────────────────────────────────────────────────┐ │  …node details… │
│ ○ People     │ │   (3D scene — nodes, edges, stacks)              │ │  [Open source →]│
│              │ └─────────────────────────────────────────────────┘ │                 │
│ AI ACTIVITY  │ ┌── AI arrangement (MCP #1269) ───────────────────┐ │                 │
│ ◌ idle       │ │ • moved "Deed 1873" → cluster A    [undo]        │ │                 │
│              │ │ • grouped 3 land docs into stack   [undo]        │ │                 │
│              │ │ • suggest: chronological layout    [apply][skip] │ │                 │
└──────────────┴─┴──────────────────────────────────────────────────┴─┴─────────────────┘
```

- The AI rail reads from the **same backend state** — the AI calls `move_node` /
  `create_stack` / `suggest-arrangement`; the view re-fetches the scene (or subscribes to the
  `WorkflowExecutionObserver`-style tick) and renders the change. "Undo" issues the inverse
  backend call. This is the **AI-as-co-editor** model: no special AI path, just the AI writing
  the same positions the human does.

**Recommendation:** mock **A1** first (sidebar mode + main-view canvas + inspector get-back-to-
source), because it expresses "rooms in the sidebar, 3D in the main view, always reach the
source" in one window. Keep **A2** as the path to the immersive/Vision-Pro window later, and
fold **A3**'s AI rail into A1 once #1269 lands. The Phase-1 reference code is A2-shaped; the
service layer (`MindPalaceService`) is reusable under any of these.

---

### Wireframe A4 — Room ↔ Sources binding (find a room by its sources; jump back)

A room is **tied to the documents / collections / smart-groups it's built from**. Each node
carries `SpatialNode.source_id`, so the set of `source_id`s in a room *is* the room's source
list. The room header surfaces those sources, and every node links back to its source document
+ inspector. This makes a room findable by its sources ("which room has the 1873 deed?") and
keeps the palace anchored to the real corpus.

```
├──────────────┬─────────────────────────────────────────────────────┬─────────────────┤
│ ROOMS      ⊕ │  Room "LFH Catalogue"        Sources ▾ (12)  + Add ▾  │ INSPECTOR       │
│ ● LFH ⟢12 src│ ┌── Sources in this room ───────────────────────────┐│ ┌─────────────┐ │
│ ○ People ⟢ 5 │ │ 📄 Deed 1873      📁 Land Collection (8)           ││ │ Node        │ │
│ ○ Mining ⟢ 9 │ │ 📄 Census 1881    ◧ Smart: "parcels>1870"         ││ │ Deed 1873   │ │
│              │ │ 📄 Survey map     …                       [Reveal] ││ │ type: source│ │
│ ▸ find room  │ └───────────────────────────────────────────────────┘│ │ source_id ✓ │ │
│   by source: │ ┌─────────────────────────────────────────────────┐  │ │             │ │
│  [deed 1873 ]│ │     ╭───────╮ (selected)                        │  │ │ ┌─────────┐ │ │
│  → LFH, Land │ │     │📄 Deed │◄── node.source_id → Deed 1873     │  │ │ │ Open     │ │ │
│              │ │     ╰───────╯                                    │  │ │ │ source → │ │ │
│              │ │                                                  │  │ │ └─────────┘ │ │
│              │ └─────────────────────────────────────────────────┘  │ │ [Reveal in  │ │
│              │  ● 12 nodes from 12 sources                           │ │  Library]   │ │
└──────────────┴───────────────────────────────────────────────────────┴─────────────────┘
```

- **Room header `Sources ▾ (12)`** — expands the distinct documents/collections/smart-groups
  this room is built from (derived from the room's nodes' `source_id`s; collections/smart-groups
  shown when a node's source resolves to one). `[Reveal]` selects that source in the Library.
- **Sidebar "find room by source"** — type/drop a document and the sidebar filters/annotates
  which rooms contain it (each `ROOMS` entry shows a `⟢N src` count). This is the
  "find a room easily by its sources" path.
- **Node → source (the get-back affordance, always present):** selecting a node shows
  `source_id ✓` and the inspector's **[Open source →]** (resolve `source_id` → `Document`,
  open in the reading surface + inspector) and **[Reveal in Library]**. A node whose
  `source_id` is nil (a native note) shows no source link.

### Wireframe A5 — Add sources to a room (drag-in + "Add to room…" picker)

Two complementary affordances, both ending in `POST /nodes` (`place_node` with a `source_id`):

**(a) Drag from the Library sidebar/grid onto the canvas** — drop a document (or a whole
collection / smart-group) into the room; each dropped item becomes a node at the drop point.

```
   Library sidebar / grid                Mind Palace canvas (drop target)
   ┌───────────────┐                     ┌─────────────────────────────────────┐
   │ 📄 Deed 1873  │ ─────drag──────────▶│        ╭───────╮  ← new node placed   │
   │ 📄 Census ▒▒▒ │   (multi-select     │        │📄 Deed │    at drop point     │
   │ 📁 Land Coll. │    or a collection) │        ╰───────╯    POST /nodes        │
   │ ◧ Smart group │                     │   "drop a collection → N nodes"       │
   └───────────────┘                     └─────────────────────────────────────┘
```

**(b) "+ Add ▾" in the room header → picker** — for when drag isn't handy (or from inside the
Mind Palace window). Search the Library; multi-select documents / a collection / a smart-group;
"Add" places one node per resolved document.

```
   Room header:  … Sources ▾ (12)   [ + Add ▾ ]
                                    └─────────────────────────────┐
                                    │  Add sources to "LFH"        │
                                    │  🔍 [ deed                ]   │
                                    │  ☑ 📄 Deed 1873              │
                                    │  ◻ 📄 Deed 1875              │
                                    │  ◻ 📁 Land Collection (8)    │  ← adds 8 nodes
                                    │  ◻ ◧ Smart: parcels>1870     │  ← adds matches
                                    │            [ Cancel ] [ Add ] │
                                    └─────────────────────────────┘
```

- Dropping/adding a **collection or smart-group** expands to its member documents and places
  one node each (or, optionally, a single node + a `SpatialStack` group — see open question).
- Drag-in obeys the SwiftUI drop lessons: a single `.onDrop(of:[UTType])` / one `Transferable`
  on the canvas, not stacked `.dropDestination`s of different types
  (`feedback_dropdestination_stacking`); keep drop modifiers inline in `body`
  (`feedback_state_binding_through_value_copy`).
- Nothing here mutates the Library — `place_node` only records that a document is *shown* in a
  room. Removing a node (`DELETE /nodes/{id}`) never deletes the document.

### How the AI-manipulation API maps to the view (the #1269 bridge)

```
   AI (MCP server #1269)                 Backend /api/mind-palace            SwiftUI canvas
   ─────────────────────                 ───────────────────────            ──────────────
   "move Deed to (3,1,0)"   ──►  PATCH /nodes/{id}  (move_node)   ──►  re-fetch GET /nodes
   "group these 3"          ──►  POST /stacks + add_to_stack      ──►  re-fetch GET /stacks
   "arrange chronologically"──►  POST /rooms/{id}/suggest-arrangement ► positions update
   "look here"              ──►  POST /rooms/{id}/viewport (save) ──►  camera animates
   "capture this view"      ──►  POST /rooms/{id}/capture         ──►  bookmark in viewport
```

The Swift view is a **pure renderer of backend scene state**, so a human drag and an AI
`move_node` are indistinguishable to it — both mutate the same room and the view reconciles by
re-reading the scene. A lightweight "scene changed" signal (poll on focus, or reuse the
`WorkflowExecutionObserver` pattern) keeps the canvas live while the AI works.

### New Swift files (Mind Palace, when approved to build)

| File | Role | Calls |
|---|---|---|
| `Services/MindPalaceService.swift` *(exists, reference)* | typed-client wrapper | all `/api/mind-palace` |
| `Models/SpatialModels.swift` *(exists, reference)* | view-models | — |
| `Views/MindPalace/SpatialView.swift` *(exists, 2D read-only)* | canvas host | nodes/connections/viewport |
| `Views/MindPalace/SpatialScene3D.swift` *(new — Phase 2)* | RealityKit `RealityView` scene | renders SpatialNode x/y/z + rotation + scale |
| `Views/MindPalace/RoomListView.swift` *(new)* | sidebar rooms + stacks + 3D/2D toggle | `/rooms`, `/stacks` |
| `Views/MindPalace/SpatialNodeInspector.swift` *(new)* | node details + **Open source** affordance | resolves `source_id` → `Document` |
| `Views/MindPalace/RoomSourcesBar.swift` *(new)* | room header `Sources ▾` (distinct source docs/collections/smart-groups) + Reveal | derived from nodes' `source_id` |
| `Views/MindPalace/AddToRoomPicker.swift` *(new)* | "+ Add ▾" picker + canvas drop target → place nodes | `POST /nodes` (`place_node`) |
| `Views/MindPalace/ArrangementMenu.swift` *(new)* | Arrange ▾ + AI activity rail | `suggest-arrangement`, `focus` |
| `Models/FeatureManager.swift` *(edited, exists)* | `isMindPalaceEnabled` | — |

### OPEN QUESTIONS — Mind Palace

1. **First surface: A1 sidebar-mode or A2 separate window?** A1 is consistent with the app and
   keeps the inspector; A2 is the cleaner path to a Vision-Pro `ImmersiveSpace` later and is
   what the reference code already does. Which do we mock first?
2. **RealityKit vs SceneKit for the canvas?** RealityKit is the Vision-Pro path (and your stated
   target) but is heavier on macOS and has a different camera model; SceneKit is lighter for a
   desktop 2.5D scene. Do we go RealityKit now (forward-compatible) or prototype in SceneKit/2D
   and swap later?
3. **What does a "node" *look* like in 3D?** A flat card standing up? A thumbnail plane? A
   labeled cube? Different `node_type`s (source/claim/note/entity/transcription) — same shape
   tinted, or distinct geometry?
4. **Rooms vs library hierarchy — how does a doc get *into* a room?** Drag from Library sidebar
   onto the canvas? An "Add to room ▾" on any document? Auto-populate a room from a folder /
   smart-group / catalogue? (Backend `place_node` takes a `source_id`.)
5. **AI co-editing UX (#1269):** when the AI re-arranges, does the view animate live, or stage
   changes for the human to accept/undo (A3 rail)? Who "owns" the camera when both are acting?

---

## Part 2 — RESEARCHER

### The vision (Daniel)

A **sidebar button → Projects**. Within a project, a workspace with three faces:

- a **chat** (conversation about the project),
- a **web browser** (the research tools — `web-search`, `browser-navigate`, `document-fetch`
  — already implemented in the backend, SSRF-guarded),
- **project tasks + milestones** (Project → Plan → Task → Step, plus notes / checklists /
  sources — all backend CRUD exists).

**No autonomous agent runner exists, and building one is out of scope.** Researcher is a
*manual, tool-assisted* workspace: the human (or, later, the chat) drives searches; results
get saved into notes/sources.

### Backend already provides (`/api/research`)

| Panel | Models | Endpoints |
|---|---|---|
| Projects list | Project | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}` |
| Plans / milestones | Plan | `GET /projects/{id}/plans`, `POST /plans`, `GET/PATCH /plans/{id}`, `GET /plans/{id}/tasks` |
| Tasks | Task | `POST /tasks`, `GET/PATCH /tasks/{id}`, `GET /tasks/{id}/steps` |
| Steps | Step | `POST /steps`, `PATCH /steps/{id}` |
| Notes | Note | `GET /projects/{id}/notes`, `POST /notes`, `GET/PATCH /notes/{id}` |
| Checklists | Checklist | `GET /projects/{id}/checklists`, `POST /checklists`, `PATCH /checklists/{id}/items/{item_id}` |
| Sources | Source | `GET /projects/{id}/sources`, `POST /sources` |
| Web tools | — | `POST /tools/web-search`, `POST /tools/browser-navigate`, `POST /tools/document-fetch` |

Chat reuses the **existing** conversation/chat services (the app already has
`ChatServiceGenerated` / `ConversationServiceGenerated`), scoped to a project.

---

### Wireframe R1 — Sidebar Projects list + 3-pane project workspace (RECOMMENDED)

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│  ◳  Fichero — Researcher                                                              │
├──────────────┬─────────────────────────────────────────────────────────────────────┤
│ [📁][🔍][⚡][🔬]│  Project: "Land tenure 1870s"                                        │
│  ▲ mode bar  │ ┌────────────┬──────────────────────────┬──────────────────────────┐ │
│              │ │ CHAT       │  WEB BROWSER             │  TASKS & MILESTONES        │ │
│ PROJECTS   ⊕ │ │ ─────────  │  ┌────────────────────┐ │  ▾ Milestone: Survey       │ │
│ ● Land tenure│ │ you: find  │  │🔍 [land deed 1873  ]│ │   ☑ Pull deeds (done)      │ │
│ ○ Mining law │ │  deeds re  │  │ ↻ ⌂ https://…       │ │   ◻ Map parcels            │ │
│ ○ Water rts  │ │  parcel 12 │  ├────────────────────┤ │   ◻ Cross-ref census       │ │
│              │ │ ai: 3 hits │  │ <rendered page /   │ │  ▾ Milestone: Synthesis    │ │
│ ─ SOURCES ─  │ │  saved as  │  │  search results>   │ │   ◻ Draft chapter 2        │ │
│ • deed1873.._│ │  sources   │  │                    │ │                            │ │
│ • census.pdf │ │            │  │  [+ Save as source]│ │  NOTES                     │ │
│              │ │ [type…  ▶] │  │  [+ Save to notes ]│ │  • "parcel 12 = lot 4a"    │ │
│              │ └────────────┴──────────────────────────┴──────────────────────────┘ │
└──────────────┴─────────────────────────────────────────────────────────────────────┘
```

- **Sidebar:** mode bar adds a 🔬 Researcher icon; a **Projects** list (`GET/POST /projects`)
  and a **Sources** disclosure for the selected project (`GET /projects/{id}/sources`).
- **Workspace = 3 panes** via `HStack` + `ResizableDivider` (never nested
  `NavigationSplitView`/`.inspector` — `feedback_swiftui_splits`):
  - **Chat** — existing chat services scoped to the project.
  - **Web browser** — search box → `POST /tools/web-search`; navigate →
    `POST /tools/browser-navigate`; fetch a doc → `POST /tools/document-fetch`. Results render
    in-pane with **[+ Save as source]** (`POST /sources`) and **[+ Save to notes]**
    (`POST /notes`).
  - **Tasks & milestones** — Plans (milestones) → Tasks → Steps tree
    (`GET /projects/{id}/plans`, `/plans/{id}/tasks`, `/tasks/{id}/steps`); checklists inline
    (`PATCH /checklists/{id}/items/{item_id}`); notes list below.

---

### Wireframe R2 — Projects list → focused single-pane with a segmented switcher

For smaller windows: one pane at a time, switched by a segmented control. Same data, less
horizontal pressure.

```
├──────────────┬─────────────────────────────────────────────────────────────────────┤
│ PROJECTS   ⊕ │  "Land tenure 1870s"   [ Chat | Browser | Tasks | Notes | Sources ]   │
│ ● Land tenure│ ┌─────────────────────────────────────────────────────────────────┐ │
│ ○ Mining law │ │  (the selected face fills the pane — e.g. Browser)              │ │
│              │ │   🔍 [land deed 1873            ]  ↻                              │ │
│              │ │   <results>            [+ source] [+ note]                       │ │
│              │ └─────────────────────────────────────────────────────────────────┘ │
└──────────────┴─────────────────────────────────────────────────────────────────────┘
```

**Recommendation:** **R1** (3-pane) as the primary; degrade to **R2**'s segmented switcher at
narrow widths (or as a `PreviewMode`-style option). Both reuse the same panel views.

### Wireframe R3 — Per-project tracking: Archives · Search Terms · Library Destination

Daniel wants a project to track **the archives being searched**, **the search terms tried**,
the **parts of the project**, and **where findings get filed in the Library**. These surface in
the Tasks pane's left rail (or a 4th "Project" tab in R2):

```
├──────────────┬──────────────────────────────────────────────────────────────────────┤
│ PROJECT      │  "Land tenure 1870s"        Destination: 📁 /Research/LandTenure  [�edit]│
│ ─ ARCHIVES ─⊕│ ┌── Parts (Plans) ──────────┬── Search terms tried ──────────────────┐ │
│ 🏛 Archivo    │ │ ▾ Part: Survey            │  ☑ "land deed 1873"      12 hits  ↻     │ │
│    Nacional   │ │   ☑ Pull deeds            │  ☑ "parcel 12 census"     4 hits  ↻     │ │
│    ✓ accessed │ │   ◻ Map parcels           │  ◻ "escritura 1873" (es)  0 hits  ↻     │ │
│ 🏛 ACENET     │ │ ▾ Part: Synthesis         │  + add term…                            │ │
│    ◷ pending  │ │   ◻ Draft chapter 2       │  (running list, per project)            │ │
│ + add archive │ └───────────────────────────┴─────────────────────────────────────────┘ │
│              │  Findings filed to:  📁 /Research/LandTenure  (3 docs imported)          │
└──────────────┴──────────────────────────────────────────────────────────────────────────┘
```

- **Archives rail** (left) — first-class list of repositories being researched ("Archivo
  Nacional", "ACENET") with an access-status badge.
- **Parts** = the project's **Plans** (each Plan is a phase/part with its Tasks).
- **Search terms tried** — a running per-project list with hit-counts and a re-run (↻) button.
- **Destination** (header) — the target **Library folder/collection** where found materials get
  filed; "Findings filed to" shows what's landed there.

### Backend support vs. gaps (checked against `research_crud.py`, `research_notes.py`,
`research_models.py`, and the `/api/research` contract)

| # | Tracked item | Status | Backing model / field | Notes |
|---|---|---|---|---|
| 1 | **Archives** | ⚠️ **PARTIAL** | `SearchSource` (`source_type` enum `url/folder/database/api`, `label`, `url`, `description`, `access_status`, `reliability`) | An archive *can* be stored as a `SearchSource` of type `database`/`url` — `label`="Archivo Nacional", `access_status`, `reliability` all fit. But there's **no `archive` source_type** and no first-class Archive entity, so "archive" and "a web URL source" are conflated. `_build_term_plan` emits an `archives` text array into `Plan.metadata`, but those are *suggestions*, not trackable records. **Recommend**: add `archive` (and maybe `repository`) to `SearchSourceType`, or a thin `ResearchArchive` model. → **Gap G1 (optional, low).** |
| 2 | **Search terms tried** | ❌ **NEEDS NEW BACKEND** | none dedicated | `WebSearchRequest.query` is **transient** (not persisted as a list). `Plan.metadata.research_term` stores *one* term per plan as a side effect of `create_plan(term=…)`, and `_build_term_plan` expands a term — but there is **no per-project "terms tried" list with hit-counts**. **Recommend**: a `ResearchSearchTerm` model (`project_id`, `term`, `language`, `result_count`, `last_run_at`, `tool`) + `GET/POST /projects/{id}/search-terms`; or, interim, append each query to `project.metadata["search_terms"]`. → **Gap G2 (real, medium).** |
| 3 | **Different parts of project** | ✅ **SUPPORTED** | `ResearchPlan` (`project_id`, `name`, `description`, `status`, `order_index`) → `ResearchTask` → `ResearchStep` | "Parts" map cleanly onto **Plans** (a Plan = a part/phase, ordered via `order_index`). No new backend needed; if a *lighter* grouping than Plan→Task→Step is wanted, that's a UI-only simplification (show Plans as "parts", hide Steps). → **No gap.** |
| 4 | **Destination in Library** | ❌ **NEEDS NEW BACKEND** | none on `ResearchProject` | `folder_path` exists on `SavedSearch`, `Workflow`, `Conversation`, etc., but **not on `ResearchProject`**. There is no link from a project to a target Library folder/collection where findings land. **Recommend**: add `target_folder_path: str | None` (or `library_destination`) to `ResearchProject`. Per the **0.0.x no-migration rule**, add the field to the Pydantic model + `_ensure_table` (no ALTER). Interim: `project.metadata["target_folder_path"]`. Also needs the "file this source into the Library" action (ties to Researcher open-question #5). → **Gap G3 (real, medium).** |

### Backend gaps to file as separate tasks (design-flagged, not implemented here)

- **G1 (optional):** Extend `SearchSourceType` with `archive`/`repository`, **or** add a thin
  `ResearchArchive` model + `GET/POST /projects/{id}/archives`. Lets archives be tracked as
  first-class items rather than overloading generic sources.
- **G2 (required for "search terms tried"):** Add `ResearchSearchTerm`
  (`project_id`, `term`, `language`, `result_count`, `last_run_at`, `tool`) with
  `GET/POST /projects/{id}/search-terms`, and have `web-search` optionally record the query
  against the project. Interim path: persist into `project.metadata["search_terms"]`.
- **G3 (required for "destination in Library"):** Add `target_folder_path` to
  `ResearchProject` (model + `_ensure_table`, no ALTER per 0.0.x rule) and a "file source into
  Library" action that imports a fetched document into that folder as a real `Document`.

> The 3-pane Researcher UI (R1/R2) ships **without** G1–G3 using what exists today (Plans as
> parts, sources, notes, web tools). Archives (interim via `SearchSource`), search-terms, and
> Library-destination panels light up fully once the gaps land — they should be **filed now**
> so the UI and backend converge.

### New Swift files (Researcher, when approved to build)

| File | Role | Calls |
|---|---|---|
| `Services/ResearchService.swift` *(new)* | typed-client wrapper | all `/api/research` incl. tools |
| `Models/ResearchModels.swift` *(new)* | view-models for Project/Plan/Task/Step/Note/Checklist/Source | — |
| `Views/Research/ResearchProjectListView.swift` *(new)* | sidebar projects + sources | `/projects`, `/sources` |
| `Views/Research/ResearchWorkspaceView.swift` *(new)* | 3-pane (HStack + ResizableDivider) host | — |
| `Views/Research/ResearchChatPane.swift` *(new)* | project-scoped chat | existing chat services |
| `Views/Research/ResearchBrowserPane.swift` *(new)* | web search/navigate/fetch + save | `/tools/*`, `POST /sources`, `/notes` |
| `Views/Research/ResearchTasksPane.swift` *(new)* | plans (parts)→tasks→steps + checklists + notes | `/plans`,`/tasks`,`/steps`,`/checklists`,`/notes` |
| `Views/Research/ResearchProjectPane.swift` *(new)* | Archives rail + Search-terms list + Library-destination header (R3) | `/sources` (archives interim), G2 search-terms, G3 destination |
| `Models/FeatureManager.swift` *(edit)* | add `isResearchEnabled` flag | — |

> `ResearchProjectPane` renders against what exists today (archives as `SearchSource`s, Plans
> as parts) and lights up the search-terms + destination affordances once gaps **G2/G3** land.

### OPEN QUESTIONS — Researcher

1. **Web browser pane: rendered HTML or structured results?** `document-fetch` returns content
   (likely text/markdown), `web-search` returns hits. Do we render a real web view
   (`WKWebView`) for navigation, or a sanitized text/markdown reader of fetched content? (A
   `WKWebView` raises the SSRF/sandbox surface that the backend tools were built to avoid.)
2. **Chat scope & engine:** is the project chat the *same* conversation system as the main app
   (just tagged to a project), or a distinct research conversation? Which model/provider drives
   it, and is it user-editable (per `feedback_user_editable_not_hardcoded`)?
3. **Tasks/milestones vs the app's GitHub backlog:** Researcher's Plan→Task→Step is *project
   research* tasks, not Fichero dev issues — confirm these stay independent of the GitHub
   workflow and never sync.
4. **Sidebar mode or window?** Mind Palace may go to a window (Vision Pro); should Researcher
   be a **sidebar mode** (R1) consistently, or also a window? (Recommend sidebar mode — it's a
   reading/writing workspace, not an immersive surface.)
5. **Sources ↔ Library:** when you "Save as source", is a Source just a URL+metadata record, or
   does it also **import the fetched document into the Library** (becoming a real `Document`
   the rest of Fichero can catalogue/transcribe)? This is the bridge between Researcher and the
   document corpus.

---

## Shared decisions (both features)

- **Flags:** add `research` + `mindPalace` `@AppStorage` flags to `FeatureManager`, default OFF,
  bump `releaseProfileVersion`. (Mind Palace flag already added on `opus` reference commit.)
- **Rendering-only contract:** Swift renders/persists backend state; no client-side layout,
  dedup, or arrangement (`feedback_kg_logic_in_backend`). This is what makes the AI and human
  share one palace.
- **Split layout:** `HStack` + `ResizableDivider`, never nested `NavigationSplitView` /
  `.inspector` (`feedback_swiftui_splits`).
- **File registration:** every new `.swift` via `ruby scripts/add-swift-file.rb` (Rule 10).
- **S0 tier decision (open):** promote `mind_palace.router` + `research_agents.router` from
  `_DEV` to `_CORE` so shipped release builds serve them (today only the dev-tier embedded
  engine does). Needs Daniel/#1151 sign-off.

---

## Summary

**Mind Palace** — A RealityKit 3D space (Vision-Pro-bound) where archival materials are laid
out, grouped, and layered, and where the **AI is a co-editor** that re-arranges the same room
the human does, because positions/stacks/camera are all backend state the AI drives through
the same `/api/mind-palace` endpoints (the #1269 MCP bridge). Rooms are a workspace layer
*separate* from the library hierarchy — a view, not a container — and from any node you can
always jump back to the source document + inspector. Three layout variants are drawn: **A1**
sidebar-mode + main-view canvas + inspector (recommended first mock), **A2** separate window
(today's reference code; the path to an immersive Vision-Pro space), and **A3** A1 plus an AI-
arrangement rail. A room is **tied to its sources** (each node's `SpatialNode.source_id`): the
room header lists the documents/collections/smart-groups it's built from (so a room is findable
by its sources), every node jumps back to its source document + inspector (**A4**), and an easy
**add-sources** flow (drag from Library + an "+ Add ▾" picker, both calling `place_node`)
populates the room without touching the Library (**A5**) — all backend-supported today. Open
questions center on A1-vs-A2, RealityKit-vs-SceneKit, what a 3D node looks like, how docs enter
a room, and the AI co-editing UX.

**Researcher** — A sidebar **Projects** workspace: pick a project, work in a 3-pane layout of
**Chat | Web browser | Tasks & milestones** (with notes/checklists/sources), all backed by the
complete `/api/research` CRUD + the SSRF-guarded `web-search`/`browser-navigate`/`document-fetch`
tools. It is **manual and tool-assisted — no autonomous agent runner** (explicitly out of
scope). **R1** (3-pane) is recommended, degrading to **R2** (segmented single-pane) at narrow
widths. Per-project tracking (**R3**) adds **Archives**, **Search terms tried**, project
**Parts**, and a **Library destination** — a backend check shows Parts map to existing
**Plans** (✅) and Archives partly fit existing **`SearchSource`** (⚠️), but **search-terms**
and **Library-destination** need new backend (**gaps G2 + G3**, with optional **G1** to make
archives first-class); all three are flagged to file as tasks so UI and backend converge. Open
questions: rendered-web-view vs text reader for the browser pane, chat scope/model, keeping
research tasks independent of the GitHub backlog, sidebar-mode placement, and whether "Save as
source" also imports the doc into the Library corpus.
