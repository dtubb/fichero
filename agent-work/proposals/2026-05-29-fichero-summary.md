# Fichero — Wireframe Summary

**2026-05-29.** Tight version. The app isn't bad right now — these are the decisions to collapse duplicates and ship a single-path UI.

## The model

**One library, many views.** Tinderbox-style: the library is the container, not a mode. Pages are atomic; entities/annotations are tied to pages; chapters/sections/citations are aggregations.

**Collections are the unit; views are independent of container type.** A *folder* and a *workspace* are both collections — a workspace is just a folder with curated items (sources, annotations, quotes). Folder views == workspace views: **list / map / WebKit graph / RealityKit 3D**. Same four lenses, user picks.

- "Mind Palace" = the RealityKit view of any folder/workspace
- The container doesn't dictate the view; the user picks.

**Researcher is top-level, not a view.** Researcher is its own sidebar area — an active working environment (browser + tasks + chat) for *doing* research on the web. It is NOT a view of a folder/workspace; it's a peer to the library. Its outputs (saved pages, notes, citations) flow back into folders/workspaces inside the library.

## The shape

```
┌─ SIDEBAR ──────────┬─ CONTENT (3-column) ────────────────────┬─ INSPECTOR ─┐
│ ▾ My Library       │ ┌──LIST──┐ ┌─ MIDDLE VIEW ─┐ ┌─PREVIEW─┐ │ Artifacts   │
│   ▾ tubb2020.pdf   │ │ entity │ │ list / map /  │ │ [page   │ │ Entities    │
│     • p.2 [sel]    │ │ /doc/  │ │ WebKit graph /│ │  image] │ │ Knowledge   │
│ ─────────          │ │ source │ │ RealityKit /  │ │         │ │  Graph      │
│ ⚡ Workflows       │ │ list   │ │ Research panes│ │         │ │ Citations   │
│ ⏱ Activity         │ └────────┘ │  per scope)   │ └─────────┘ │ Annotations │
│ 🗂 Workspaces       │             └───────────────┘             │             │
│   • Tubb 2020       │                                          │             │
│   • Chocó field…    │                                          │             │
│ 🔬 Researcher       │
│ 🔎 [Search bar]    │                                          │             │
└────────────────────┴──────────────────────────────────────────┴─────────────┘
```

- **Sidebar** = library tree + per-feature sections (Workflows, Activity, Workspaces, Search). No separate icon strip.
- **Content middle column** = the view picker: list / map / WebKit graph / RealityKit 3D. *Same collection, different lens.* The chosen view is per scope/workspace and persists.
- **Left list column** stays for entity/doc lists when relevant.
- **Right preview column** is always the source page image when the focus is on a claim/entity/quote.
- **Inspector layers (in order):** Artifacts → Entities → Knowledge Graph → Citations → Annotations. **No Map tab** — redundant with the middle-column map view.

## The rules

1. **Selection IS the scope** — sidebar selection (single, multi, folder, library root, workspace, search results) drives every view.
2. **Clicks in the inspector sync the other views, they don't change the selection.** Clicking an entity or claim focuses the middle-column view (graph/map/3D) **and** the source-page preview on that item — library-tree selection stays put. Cross-view focus, not re-navigation.
3. **Navigation never resets view state** (anchor in `@SceneStorage` / `@StateObject`).
4. **One renderer per data type.** Same KG data → one endpoint (`GET /documents/{id}/knowledge-graph?include_children=…`) → one renderer. Three drifting paths collapse to one.
5. **Source preview is always visible** when looking at claims/entities/quotes.
6. **One library.** (Multi-library is the source of the workflows/activity duplication.)
7. **Workspace = collection. Views are just lenses.** Same workspace, switch between list/map/RealityKit. No separate "Mind Palace" mode.

## What's broken (concrete fix list)

| # | Issue | Fix |
|---|---|---|
| 1 | Page-level KG empty | One endpoint with `include_children`; one renderer |
| 2 | 3 drifting KG read paths | All call the one endpoint |
| 3 | Per-claim source page not clickable in OntologyBrowser | Pass `onNavigateToSource` everywhere |
| 4 | KG view resets on navigation | `@SceneStorage` / `@StateObject` |
| 5 | Click on entity/claim doesn't sync graph + preview | Cross-view focus binding (no selection change) |
| 6 | KG quality is poor (3B oMLX) | Add `$medium` cloud tier; stop falling to 3B |
| 7 | RealityKit shows boxes, no page images | Add `thumbnailUrl` to workspace items + texture |
| 8 | Inspector Map tab duplicates middle-column views | Remove from inspector |
| 9 | "Only see the first" truncation | Show-all / load-more |
| 10 | Statements/Artifacts buttons missing | Add buttons by refresh |
| 11 | Mind Palace is a separate "mode" | It is just the RealityKit view of any folder/workspace. Keep Researcher as its own top-level sidebar area. |

## Already in flight

- 2 commits on `0.0.2`: build unblock (NodeDef + lint) + provider-aware cost log.
- 3 Codex lane branches ready to merge: `clean_text` programmatic, page-entities read-rollup, provenance label.

## Order of execution

1. **You read this** and mark up.
2. **Empirical test on the Preface PDF** (CLI → live engine → SwiftUI) to verify page-attribution on real data.
3. **Collapse the 3 KG read paths** to one endpoint (kills #1, #2, much of #3).
4. **Cross-view focus** — inspector click syncs graph + preview without changing selection (#5).
5. **State preservation** on navigation (#4).
6. **`$medium` tier** for quality (#6).
7. **Workspace = folder + views** — fold Mind Palace into "RealityKit view of any folder/workspace" (#11). Researcher stays top-level. Add page-image textures to RealityKit (#7). (#11), then add page-image textures to RealityKit (#7).
8. **Inspector cleanup**: remove Map (#8), restore clickable source, add buttons, load-more (#3, #10, #9).

That's the whole picture. The current app already does most of this well — these fixes collapse the duplicates into the working parts.
