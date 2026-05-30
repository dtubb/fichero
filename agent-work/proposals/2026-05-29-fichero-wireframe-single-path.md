# Fichero 0.0.2 — App Wireframe & Single-Code-Path Plan

**Date:** 2026-05-29
**Purpose:** Give Daniel a thinkable picture of the whole app shape so we can collapse duplicate paths into one canonical UI + code path before piling on more fixes.
**Companion to:** the 2026-05-29 KG code review (defect list inline below).

---

## 1. The Shell — three panes + a mode bar

```
┌──┬──────────────┬─────────────────────────────┬───────────────┐
│M │  Sidebar     │       Content               │  Inspector    │
│o │  (mode-      │  (the work — PDF view,      │  (right-side  │
│d │  specific)   │   KG browser, Mind Palace,  │   metadata +  │
│e │              │   workflow editor, ...)     │   KG + claims │
│  │              │                             │   for the     │
│B │              │                             │   selected    │
│a │              │                             │   thing)      │
│r │              │                             │               │
└──┴──────────────┴─────────────────────────────┴───────────────┘
```

The **Mode Bar** is the leftmost icon strip — currently 9 modes after the KG re-enable:

| # | Mode            | Icon                                  | What it owns                                   |
|---|-----------------|---------------------------------------|------------------------------------------------|
| 1 | Library         | folder                                | document tree, inbox, folders                  |
| 2 | Search          | magnifyingglass                       | saved searches + search bar                    |
| 3 | Chat            | bubble.left.and.bubble.right          | RAG conversations                              |
| 4 | Workflows       | bolt                                  | workflow definitions, editor                   |
| 5 | Automation      | gearshape.2                           | schedules + triggers                           |
| 6 | Activity        | clock                                 | workflow runs + logs                           |
| 7 | **Knowledge Graph** | point.3.connected.trianglepath.dotted | OntologyBrowser: entity list + graph + claims |
| 8 | Mind Palace     | cube.transparent                      | spatial 3D arrangement of sources              |
| 9 | Research        | flask                                 | research project workspace                     |

**Inline duplicate to kill:** Library mode currently also shows "Workflows", "Activity", "Knowledge Graph" as nav rows *inside* its sidebar list — so each one is reachable two ways (mode bar icon **and** inline row). Pick one. Recommended: keep the **mode bar as the single switch**; remove the inline rows from library sidebar (or keep them only as quick-jump shortcuts with no separate render path).

---

## 2. The Library mode — current sidebar shape

```
┌─ MODE BAR ┬─ LIBRARY SIDEBAR ────────────────┐
│ [1] Lib   │  > Inbox                          │
│ [2] Srch  │    > My Book                      │
│ [3] Chat  │      • tubb2020shift - Preface    │
│ [4] Work  │      • tubb2020shift - Ch 1       │
│ [5] Auto  │  > Images                         │
│ [6] Act   │  ──────                           │
│ [7] KG    │  ⚡ Workflows   ← duplicate of #4 │
│ [8] Mind  │  ⏱ Activity    ← duplicate of #6 │
│ [9] Rsrch │  ● KG          ← duplicate of #7 │
└───────────┴───────────────────────────────────┘
```

**Decision needed:** keep inline rows or kill them?
- Keep → they must route to the SAME content view as the mode-bar icon, no parallel renderer.
- Kill → the mode bar becomes the only switch; library sidebar shows only documents.

---

## 3. The Knowledge Graph — single render path (the big collapse)

This is where the code review found the worst duplication. There are **three** code paths today doing the same job:

```
                 ┌─ THE KG DATA ──┐
                 │  entities       │
                 │  claims         │
                 │  source pages   │
                 └────────┬────────┘
                          │
   ┌──────────────────────┼──────────────────────┐
   │                      │                      │
   ▼                      ▼                      ▼
PATH A                  PATH B                 PATH C
KG sidebar mode        Document inspector     OntologyBrowser
(OntologyBrowser)      (KG tab)               (entity detail panel)
  • uses                 • uses                 • uses
    listClaims()           listClaims() +         listClaims(entityId:)
    + entity fan-out       entity fan-out         + separate
                                                  load logic
   ↑                      ↑                      ↑
   CALLS /api/claims     CALLS /api/claims    CALLS /api/claims
   (manual fan-out)      (manual fan-out)     (manual fan-out)

       ALL THREE DRIFT INDEPENDENTLY. NONE USES THE CANONICAL ENDPOINT.
```

**The canonical endpoint already exists** and the CLI already uses it:
`GET /documents/{id}/knowledge-graph?include_children=<bool>` — it collapses absorbed entities, dedups by canonical name, restores the Dates group, and rolls up children.

**Single-path proposal:**

```
                                   ┌──────────────────────────────────┐
ANY KG VIEW (sidebar / inspector / ─→  GET /documents/{id}/knowledge-  │
 entity detail) renders the SAME    │  graph?include_children=true     │
 grouped response from ONE call.    └──────────────────────────────────┘
```

- KG sidebar mode = same call against the library's root.
- Document inspector KG tab = same call against the selected doc id (page, PDF, or folder).
- OntologyBrowser entity detail = filters the same response by entity id (or a thin per-entity variant that reuses the same grouping logic).

This kills the three drifting paths in one move.

---

## 4. The right-side Inspector — current tabs

When you select a document (any kind — page, PDF, folder), the inspector shows tabs:

```
┌─ INSPECTOR ──────────────────────────────────────┐
│ [📄 Content] [✏️ Edit] [● KG] [🗺️ Map] [📦 Art.] [ⓘ Info] │
│ ─────────────────────────────────────────────── │
│  KG tab content (when selected):                 │
│  ┌────────────────────────────────────────┐    │
│  │ ▾ 👥 People (76)                  ⟳ ⚙ │    │  ← refresh + (proposed)
│  │   Don Alfonso  (10 claims)  →   ⭐    │    │     2 new buttons:
│  │     was a 21st-century artisanal miner │    │     • get statements
│  │     (Don Alfonso) (was) (...miner)     │    │     • get artifacts
│  │     ⟶  p. 4  (CLICKABLE — jumps to     │    │
│  │              page 4 in PDF view)       │    │
│  │   Esteban  (8 claims)  →               │    │
│  │   ...                                  │    │
│  │ ▾ 🏢 Organizations (12)                │    │
│  │ ▾ 📍 Places (24)                       │    │
│  │ ▾ 📅 Dates (5)                         │    │
│  │ ▾ ⚡ Events  ← currently sparse —      │    │
│  │              extraction-quality issue  │    │
│  └────────────────────────────────────────┘    │
└──────────────────────────────────────────────────┘
```

**Required regressions to restore:**
- **Per-claim source page** must always be visible and clickable → posts `.ficheroOpenClaimSource` → navigates the PDF view to that page. Already exists in the DocumentInspector path (`EntityKindRow` arrow button); **missing** in the OntologyBrowser entity detail. (Defect 3.)
- **Buttons by the refresh control:** "Get statements" + "Get artifacts" — affordances to fetch on demand rather than waiting on a workflow tick.
- **Truncation fix:** "doesn't this just let us see the first[?]" — the inspector groups are paginated; add a clear "show all / load more" affordance.

---

## 5. Mind Palace — must use RealityKit AND show page images

Current state (per the code review):
- RealityKit path exists (`#if canImport(RealityKit)`), falls back to 2D otherwise. ✓
- `SpatialScene3D.buildScene()` builds nodes as plain colored boxes (`SimpleMaterial`). ✗
- No code anywhere loads page thumbnails / document images. ✗
- No tap-to-select gesture on 3D nodes — explicitly deferred in the file's comment. ✗

Required:

```
┌─ MIND PALACE (RealityKit canvas) ─────────────────────────┐
│   Each node = a document/page card with the actual        │
│   page image textured onto a 3D plane.                    │
│                                                            │
│       ┌─────────┐    ┌─────────┐    ┌─────────┐           │
│       │ Page 2  │    │ Page 4  │    │ Page 7  │           │
│       │ [image] │    │ [image] │    │ [image] │           │
│       └─────────┘    └─────────┘    └─────────┘           │
│         arrange ▾   • drag in 3D                          │
│                     • click → open page                   │
└────────────────────────────────────────────────────────────┘
```

Minimal data + code changes:
- Add `thumbnailUrl: String?` to `MindPalaceNode`.
- `makeNodeEntity` → async-load that image + apply as `UnlitMaterial` texture on a plane Entity.
- Wire a tap gesture → `selectedNodeId` → opens source.

---

## 6. The model question — why the KG is wrong

Not a UI issue, but it shapes the wireframe because the inspector quality is bounded by the model. Per the code review (Defect 5):

```
extraction request
        │
        ▼
   $small = Apple Intelligence
        │
        ├─ succeeds on supported locales         → ✓ good claims
        │
        └─ UnsupportedLocaleError /              → falls back to $large
           GuardrailViolationError                  = omlx Qwen 3B
                                                  ⚠ noisy, often wrong
                                                  ⚠ drops connection on
                                                    big-context entities
                                                    (Air OOM)
```

**The structured fallback to a 3B is the quality regression.** The wireframe-level fix: either
- introduce a `$medium` tier (e.g. gpt-4o-mini) as the structured fallback before the local 3B, OR
- configure `$large` to a cloud model, OR
- add a prompt/HTML escape that lets Apple do free-form extraction parsed locally (no schema → Apple doesn't reject).

---

## 7. Single-code-path consolidation list

The collapses to do, in priority order:

| # | Today (duplicate)                                                            | Tomorrow (single path)                                              |
|---|-------------------------------------------------------------------------------|---------------------------------------------------------------------|
| 1 | 3 KG read paths: KG sidebar / inspector KG tab / OntologyBrowser entity detail | All call `GET /documents/{id}/knowledge-graph?include_children=…`   |
| 2 | Mode-bar entries duplicated as inline rows in Library sidebar                 | Pick one. (Recommend: mode bar = the switch; remove inline rows.)   |
| 3 | Click-to-source wired in DocumentInspector path, missing in OntologyBrowser   | Single `onNavigateToSource` closure passed wherever claim rows render |
| 4 | Two backend KG endpoints: `/inspector` (exact-match) and `/knowledge-graph` (rollup) | Deprecate `/inspector`; everything reads `/knowledge-graph`.   |
| 5 | Structured extraction split: Apple → falls back to 3B with quality cliff      | Insert a `$medium` cloud tier between Apple and the local 3B.       |
| 6 | Mind Palace 3D node = box AND a separate 2D fallback canvas                   | One scene builder; texture page-image regardless of 3D/2D mode.     |

---

## 8. Questions for Daniel to think about

1. **Library sidebar inline rows** (Workflows / Activity / KG): keep as quick-jump shortcuts, or kill since the mode bar already lists them?
2. **KG sidebar mode (#7) vs Library inspector KG tab:** is the KG mode a *separate workspace* (entity-first), and the inspector KG tab a *contextual view for the selected document*? If so they're complementary, not duplicates — but the **render** path is shared (#1 above).
3. **Mind Palace primacy:** is Mind Palace the **default** way to browse a library (visual / 3D), with the Library mode as the list/grid fallback? Or always-secondary to the document list?
4. **Inspector "Get statements / Get artifacts" buttons:** what's their semantics — re-fetch from DB (cheap), re-run extraction (expensive workflow), or something between?
5. **Claim source clickability:** when clicked, should it open the PDF view *and* highlight the source text span (char_start/char_end already in `.ficheroOpenClaimSource`), or just jump to the page?

---

## 9. What this unblocks

Once the shape above is agreed:
- The KG read-path collapse (item #1) is a tightly-scoped backend + SwiftUI patch — one PR.
- The click-to-source restore (item #3) is one SwiftUI patch.
- The $medium tier (item #5) is one llm.py change + a config addition.
- Mind Palace page-image rendering (item #6) is one SpatialScene3D change + a small model field.

**Estimated:** 4 focused PRs to collapse the KG UI into a single coherent path with restored quality + clickable sources + working Mind Palace. None of them needs a wireframe rewrite — they all execute against *this* document.

---

*End of wireframe doc. Discuss; edit; we ship from this.*

---





### Final design notes (post-synthesis)

- **WebKit graph IS the KG view** (not list-with-graph-toggle): the rich render is the primary; lists are secondary.
- **Researcher / Comparison move out of the mode bar** — they belong in the sidebar as project workspaces, not top-level views.
- **Three-column KG layout** — the KG view is not the graph alone. It is **list | graph (or KG detail) | page preview**, with the page image of the current source always visible alongside. So when the user inspects an entity or claim, they can see the actual page it comes from — the KG is always grounded in its source. Same principle applies to Mind Palace and any view that surfaces claims: source preview is part of the layout, not a separate navigation step.

```
┌─ KG VIEW (three-column) ──────────────────────────────────────────────────┐
│ ┌── ENTITY LIST ──┐  ┌── GRAPH / DETAIL ──┐  ┌── PAGE PREVIEW ──────┐    │
│ │ People (76)     │  │   ●─was─●─was─●     │  │ ┌──────────────────┐ │    │
│ │   Don Alfonso 10│  │  Colombia Bogotá    │  │ │ [page image      │ │    │
│ │   Esteban    8 │  │  Claudia            │  │ │  rendered here]  │ │    │
│ │ Orgs (12)       │  │                     │  │ │                  │ │    │
│ │ Places (24)     │  │  claims + sources   │  │ │                  │ │    │
│ │ ...             │  │                     │  │ └──────────────────┘ │    │
│ └─────────────────┘  └─────────────────────┘  │  p.4 · tubb2020shift │    │
│                                                └──────────────────────┘    │
└────────────────────────────────────────────────────────────────────────────┘
```
- **KG mode fully collapses** — correcting the §10 synthesis: the WebKit graph does NOT need full-window real estate; it renders fine inside a column of the three-column layout. So KG does not survive as a separate mode either. Whole-library KG = Library mode with library-root selected + KG inspector layer (with the three-column source preview). Folder/page KG = same view with that scope. There is no KG mode.

**Revised surviving modes:** Workflows (with Activity tab), Mind Palace, Research. Everything else lives in Library + Inspector under the scope-from-selection rule.
- **State preservation on navigation:** clicking a KG element to navigate must NOT reset KG view state (selection, scroll, expansion). Anchor in @SceneStorage / @StateObject so parent re-renders do not wipe.

---

## The Plan (as of 2026-05-29, evening)

### Framing (your insight)
**One library, many views** — the Tinderbox model. The app shape is already right; we collapse into it, not redesign.

### The shape
```
Mode bar  │  Library tree  │   Content       │   Inspector
(views)   │  (selection =  │   (active view) │   (per-page
          │   the scope)   │                 │    detail)
```
- Mode bar = alternate visualizations of the *same* library
- Library tree = navigation; the selection IS the scope
- Inspector layers, in order: **artifacts → entities → KG → citations → annotations**

### Core principles
1. **One library** (multi-library is the root of the workflows/activity duplication — collapse it).
2. **Pages are atomic.** Entities tied to pages or page-groups; annotations tied to pages; chapters/sections/citations are aggregations.
3. **Scope is a SET, not a single item.** Sources: single selection / multi-selection / folder / whole library / **search result set**.
4. **Selection changes scope; never resets other views' state.** (Fixes the "UI jumps around then resets" regression.)
5. **No multiple code paths.** Same data → one renderer.
6. **WebKit graph IS the KG view** — not a list-with-graph-toggle.
7. **Some things belong in the sidebar, not the mode bar** (Researcher, Comparison probably leave the mode bar).

### What's broken — concrete fix list

| # | Issue | Layer | Fix shape |
|---|-------|-------|-----------|
| 1 | Page-level KG empty (claims live on container) | backend + read | One endpoint: `/documents/{id}/knowledge-graph?include_children=…` |
| 2 | 3 drifting KG read paths (KG sidebar, inspector, OntologyBrowser) | SwiftUI | All call the one endpoint above |
| 3 | Per-claim source page not always clickable | SwiftUI | Pass `onNavigateToSource` everywhere claims render |
| 4 | KG view resets on navigation | SwiftUI | Anchor state in `@SceneStorage` / `@StateObject` |
| 5 | KG quality is poor | backend | Insert `$medium` cloud tier; stop falling to 3B oMLX |
| 6 | Mind Palace = boxes, no page images | SwiftUI | Add `thumbnailUrl` to `MindPalaceNode` + texture in RealityKit |
| 7 | Mode bar may be redundant | design | Shrink: KG → inspector+WebKit; Researcher → sidebar |
| 8 | Statements/Artifacts buttons missing in inspector | SwiftUI | Add buttons by refresh |
| 9 | "Only see the first" truncation | SwiftUI | Show-all / load-more affordance |

### Already in flight

- **Workflow running** → wireframe section §10 (one library / many views / scope-from-selection / mode-bar shrinkage / state preservation). Will be appended above this Plan section when it lands.
- **3 Codex lane branches** waiting to merge: `clean_text` programmatic, page-entities read-rollup, provenance label.
- **2 commits on `0.0.2`**: build-unblock (NodeDef + lint) + provider-aware cost log.
- **KG sidebar row** in working tree (uncommitted, build-verified — may roll into the mode-bar shrinkage decision).

### Order of execution

1. **Wireframe v2** lands → you read + mark up on phone.
2. **Empirical test on the Preface PDF** (CLI → live engine → SwiftUI) to settle page-attribution on real data.
3. **Collapse the 3 KG read paths** → one endpoint. Single fix kills #1, #2, much of #3 in one stroke.
4. **State preservation** (#4).
5. **Quality fix** — `$medium` cloud tier (#5).
6. **Mind Palace page-image render** (#6).
7. **Mode-bar shrinkage decision** (#7) — driven by your read of the wireframe.
8. **Inspector additions**: clickable source restore, statements/artifacts buttons, load-more (#3, #8, #9).

---

---

## 11. The biggest call — no mode bar at all

Daniel: *"preview is always there. works well. webkit is beside it, works well too. sidebar works well, except duplicates. I don't think we need [a] mode bar."*

This collapses the wireframe to its final form. **The mode-bar icon strip goes away entirely.** The 9 modes that were on it dissolve into the three panes that already exist:

```
┌─ SIDEBAR ────────────┬─ CONTENT (3-column) ────────────────────┬─ INSPECTOR ─┐
│ ▾ My Library         │ ┌──LIST──┐ ┌──WEBKIT/GRAPH──┐ ┌─PREVIEW─┐│ Artifacts   │
│   ▾ Research/        │ │ entity │ │  ●─was─●       │ │ [page   ││ Entities    │
│     ▾ tubb2020.pdf   │ │ list   │ │  graph         │ │  image] ││ Knowledge   │
│       • p.1          │ │ or doc │ │  or WebKit     │ │         ││  Graph      │
│       • p.2 [sel]    │ │ list   │ │  view          │ │         ││ Citations   │
│     ▾ tubb2020-ch1   │ └────────┘ └────────────────┘ └─────────┘│ Annotations │
│   > Inbox            │                                          │             │
│ ─────────────         │                                          │             │
│ ⚡ Workflows         │                                          │             │
│ ⏱ Activity          │                                          │             │
│ 🔬 Research          │                                          │             │
│ 🧊 Mind Palace       │                                          │             │
│ 🔎 [Search bar]      │                                          │             │
└──────────────────────┴──────────────────────────────────────────┴─────────────┘
```

Where each erstwhile "mode" lives now:

| Erstwhile mode | New home |
|---|---|
| Library | The sidebar tree IS the library — it's the chrome, not a mode |
| Search | Search bar in the sidebar header; results scope the views |
| Chat | Sidebar section (conversations as a list) or removed if subsumed by Research |
| Workflows | Sidebar section (workflow defs list) |
| Automation | Sidebar section (schedules + triggers under Workflows) |
| Activity | Sidebar section (runs) — or inline tab inside Workflows |
| Knowledge Graph | **No separate mode** — KG is the content layout (list + WebKit + preview) when KG is what you want to see, plus the inspector KG layer |
| Mind Palace | Sidebar section (rooms list) — spatial is a content-area layout |
| Research | Sidebar section (projects list) — workspace opens in content area |

### Why this is correct
- **Preview is always there.** The page image is part of the layout in every view that touches sources.
- **WebKit graph works beside it.** No full-window required; it lives in a column.
- **Sidebar works.** The library tree + per-feature sections is the navigation surface. The only fix is removing the duplicates with the (now-deleted) mode bar.
- **Scope is one rule.** Whatever's selected in the sidebar IS the scope; the content area renders the active view at that scope; the inspector shows the per-page detail.
- **No multiple code paths.** With one nav surface, every view reads `scope` from sidebar selection. No mode-bar-vs-inline-row duplication. No global-vs-active-library drift. No three KG read paths.

### What this changes in code (delta from §10)

The §10 synthesis kept Workflows / Mind Palace / Research as surviving modes. **They're not modes any more — they're sidebar sections.** Concretely:

- Delete `SidebarModeBar.swift` and the entire `SidebarMode` enum.
- Delete the corresponding routing in `ContentView+Navigation.swift`, `ContentView+ViewBuilders.swift`, `ContentView+State.swift`, `ContentView+Persistence.swift`, `ContentViewModifiers.swift`, `ViewMenuCommands.swift`.
- The library sidebar (`SidebarView+ViewComponents.swift`) absorbs every feature as a section: Workflows, Activity, Research, Mind Palace, plus the document tree.
- The content area becomes a single, scope-driven layout: list / WebKit / preview columns, switchable from a small content-area toolbar (not a global mode bar).
- The KG sidebar row added today gets reverted — it doesn't exist either, because there's no KG mode.

This is a much bigger collapse than §10 proposed, but it's the right one — and Daniel is right that the proof is "everything already works in those positions; we just stop duplicating them in the mode bar."

