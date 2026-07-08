(AI generated. Not reviewed.)

# SwiftUI App Structure & Naming — Reorg Plan

Milestone: **SwiftUI App Structure & Naming** (due 2026-08-22). PLAN doc for the
milestone; **no behavior changes here**. Companion to the already-committed
`research_agent_search_audit_2571.md` (surface consolidation) and the #104
vocabulary table (canonical names). Per *iterate-never-replace*: this proposes
staged, additive moves — no folder is bulldozed, no shipped surface is broken in
one step.

## Why this doc

Two recurring smells in `fichero/fichero/`:

1. **Views-soup / dumping grounds** — folders that grew past their name
   (`Views/Library/` = 65 loose files), a `Views/Components/` catch-all, and 15
   loose files sitting at the `Views/` root.
2. **Front-end ↔ back-end naming drift** — the UI renamed concepts (Mind Palace →
   Spatial/Canvas; Researcher → Agent) but the wire contract and some stores
   still carry the old names.

This maps both, flags retired cruft, and stages the cleanup against milestone
issues. It does **not** re-litigate the Researcher/Agent/Search collapse — that
lives in `research_agent_search_audit_2571.md` and is design-gated.

## Current front-end inventory

`fichero/fichero/` top level:

| Folder | Role | Notes |
|---|---|---|
| `App/` (7) | app lifecycle, window, `AppState`, `ViewSettings` | holds one stray sheet (below) |
| `Models/` (78) | stores + domain types | largest layer; `@Observable`/`ObservableObject` stores |
| `Services/` (62) | `*Generated.swift` API wrappers + manual services | |
| `Intents/` (3) | App Intents | |
| `Views/` (15 loose + 24 subfolders) | UI | see below |
| `Resources/` | assets | |

`Views/` subfolder sizes (`.swift` count):

```
65 Library      41 Workflow     28 Sidebar      17 Chat
16 Settings     15 Components    14 Activity     13 AIProviders
10 Automation    8 Search         7 Toolbars      7 ModelComparison
 5 Menu          5 MCPServers     5 Research       5 Spatial
 4 Actions       4 KnowledgeGraph 4 Notes         2 Agents
 2 Sheets        1 Auth           1 Capture        1 Integrations
                 1 Onboarding
```

## Problem 1 — dumping grounds

### `Views/Library/` (65 files, flat)
The biggest offender. It mixes at least five distinct concerns under one flat
folder: the document browser (`LibraryView*` — 9 files), PDF reading
(`PDF*Pane/View/Overlay` — 6), representations (`Representation*`,
`StackedRepresentationPanes`, `RepresentationPicker`), annotations/citations/
artifacts inspector panes (`*InspectorPane`, `*ListView`, `*DetailView`,
`Focused*` — ~15), and image viewing (already partly split into
`Library/ImageViewer/`, `Library/ImageEditor/`, `Library/DocumentInspector/`).

**Target:** finish the split that `ImageViewer/`/`ImageEditor/`/`DocumentInspector/`
already started —
- `Views/Library/Reading/` — `PDF*`, `DocumentTextReader`, `PageContentPane`,
  `ImmersiveReaderView`, reading layout.
- `Views/Library/Representations/` — `Representation*`,
  `StackedRepresentationPanes`, `DisplayAttributesStrip` (ties **UI Reform —
  Representations** milestone).
- `Views/Library/Inspector/` — `*InspectorPane`, `Annotation*`, `Citation*`,
  `Artifact*`, `Focused*`, `InspectorTab`, `InspectorPresenter` (ties **UI Reform
  — Inspector & Annotation** milestone).
- Keep `LibraryView*` + browser at `Views/Library/` root.

### `Views/Components/` (15 files)
Genuine shared leaf views (`FlowLayout`, `MarkdownText`, `StatusBadge`,
`SplittablePane`) sit next to feature-specific rows (`ScheduleRow`, `TriggerRow`,
`WorkflowExecutionRow*`, `WorkflowPreviewSheet`) that belong with their feature
(`Automation/`, `Workflow/`). **Target:** move the feature rows out; keep
`Components/` for truly cross-feature primitives only.

### `Views/` root (15 loose files)
`ContentView` + its 10 extensions are fine as a cohesive set. But
`AdaptiveAppleShellHost`, `OpenAffordances`, `ContentViewHelperViews`,
`DocumentTabView` are the per-window shell — they read better under a
`Views/Shell/` (or `App/`) grouping. Low priority; cosmetic.

## Problem 2 — front-end ↔ back-end naming drift

Canonical direction is **front-end-first** (#104 vocabulary table). Current
mismatches:

| Concept | Front-end name | Back-end / wire name | Verdict |
|---|---|---|---|
| Spatial/2D canvas | `SpatialView`, `Canvas*Store`, `Views/Spatial/` | `/api/mind-palace/...` (`...ApiMindPalaceFolders...` generated methods) | **Drift.** UI moved off "Mind Palace"; endpoints frozen on it. Backend-lane rename (#2565); FE can't fix the path. |
| Research workspace | `.research`, `ResearchStore`, `ResearchService` | `/api/research` via `research_agents.py` (**no agent logic**) | Misleading backend name; see #2571 audit. |
| Agent | *(no surface yet)* | `/api/agent-memory` | Target surface (EPIC #2067), not built. |

**Front-end action for the Mind Palace drift:** none structural until the backend
renames the path — but the *client-facing* Swift names are already correct
(`Spatial`, `Canvas`). The only FE cleanup is a comment in `CanvasLayoutStore`/
`CanvasItemStore` noting the endpoint path is the legacy "mind-palace" mount so
the next reader doesn't think Spatial is unwired. Filed as a follow-up, not done
here (touches Models, out of this milestone's 1 open issue).

## Problem 3 — Mind Palace (retired 3D rooms) removal — DONE

**Mind Palace** — the 3D-RealityKit "rooms" feature (AI-arranged pages/notes in a
RealityKit volume) — is **retired**. It is **superseded by the live spatial
library view** (the 2D `Spatial2DCanvas`, view mode "Canvas" / `.map`), which
**stays**. The two were easy to conflate because they share the `SpatialNode`
data model and the `.spatial`/room vocabulary — the distinguishing line is the
**renderer**:

| Kept (live spatial view) | Removed (Mind Palace 3D) |
|---|---|
| `Views/Spatial/SpatialView.swift` (2D projection) | `Views/Spatial/SpatialScene3D.swift` (RealityKit renderer) |
| `Views/Spatial/Spatial2DCanvas*`, `SpatialNodeThumbnail` | `Models/SpatialTheme.swift` (RealityKit colour bridge) |
| `Services/SpatialLibraryProjector`, `Models/SpatialModels*` | `FolderRealityKitSurface` (in `DocumentKGSurface.swift`) |
| view mode "Canvas" (`.map`) | view mode "Space" (`.realitykit`) + its ⌘5 menu button |

What the removal did (this pass):
- **Deleted** `SpatialScene3D.swift`, `SpatialTheme.swift`, and the
  `FolderRealityKitSurface` view; removed the "Space (⌘5)" View-menu button and
  the now-dead `SpatialViewButton` + `libraryDisplayMode`/
  `availableLibraryDisplayModes` FocusedValues that only served it.
- **Kept the `.realitykit` enum case as a hidden decode-only alias** (mirroring
  the already-retired `.spatial` alias, #2667) so persisted/`@SceneStorage`
  "RealityKit" values still decode and **migrate to `.map`** via
  `normalizedViewDisplayMode()` — no orphaned windows, every exhaustive `switch`
  keeps compiling. The RealityKit renderer is gone; the alias is one line.
- **No RealityKit import remains** in the app after this pass.

Tension flagged: EPIC **#2667** (UI Reform — Representations, other milestone)
was written to *keep* "Space (3D)" as a peer to "Canvas (2D)". This removal
overrides that per direct instruction (3D rooms retired). #2667 should be
re-scoped to Canvas-only.

### Issue / milestone cleanup

Closed as retired (3D rooms): #1158, #1297, #1343, #1376, #1432, #1455, #1479,
#1498, #271, #511.

**Milestone "Mind Palace" (#12) intentionally NOT closed yet** — it is a
grab-bag, and 5 open issues are *not* the retired 3D feature. They need
re-homing (board-organizer) before the milestone can close:

- **#2299** — backend Mind Palace cleanup (dead `/rooms/*` routes + MCP + CLI).
  **Still real, undone** — the backend half of this removal; codex/backend lane.
- **#2788** (Node Model milestone) — retire parallel mind-palace room storage;
  backend, tracks the same teardown.
- **#1433** — wire 6 Notes endpoints (Notes, not Mind Palace).
- **#1755** — georeference maps (a Maps feature; the 3D-globe uses RealityKit but
  it is not the rooms feature).
- **#821** — Apple-Intelligence Tool protocol (backend, mis-milestoned).
- **#2300** — guardrail debt (mis-milestoned).

## Problem 4 — other retired / stale cruft

- **`SidebarMode` numbering comments are fossils** (`App/ViewSettings.swift`):
  cases run `1,2,3,4,5,6,8,9` — a `7` gap, and `shortcut()` stops at `6` so
  `research`/`knowledgeGraph` have no ⌃⌘ shortcut. Either stale comments or
  missing shortcuts. Cheap, self-contained fix — candidate first slice.
- **`CollectionWorkspaceStub.swift`** (`Views/Library/`) — name says stub; verify
  it's still referenced or delete (dead-code check before removal).
- **`IntegrationsPlaceholderSheet.swift` in `App/`** — a placeholder sheet living
  in the lifecycle folder; belongs in `Views/Sheets/` or `Views/Integrations/`,
  or is removable if Integrations shipped.
- **`Views/Integrations/` (1 file)** — single-file folder; fold into a sibling if
  it stays a placeholder.

## Target structure (staged, additive)

Nothing moves in this doc. Order of operations, smallest-first:

- **Stage 1 (this milestone, #2571-adjacent):** the `SidebarMode` comment/shortcut
  fossil fix — pure, self-contained, testable. Confirm/close #2571 against the
  existing audit.
- **Stage 2 (UI Reform milestones):** split `Views/Library/` into `Reading/`,
  `Representations/`, `Inspector/` as those milestones touch the files anyway —
  reorg rides the feature work instead of a risky standalone move (needs
  `add-swift-file.rb` pbxproj re-registration per moved file).
- **Stage 3 (Components hygiene):** relocate feature-specific rows out of
  `Views/Components/`.
- **Stage 4 (naming, backend-gated #2565):** Mind Palace → Spatial endpoint
  rename in the backend lane; FE regenerates the client, drops the legacy method
  names. Not a FE-initiated change.

## Scope note

Folder moves require `scripts/add-swift-file.rb` re-registration (main target
uses PBX file references, not sync'd groups) — so each move is a real diff, not a
free `git mv`. That's why Stage 2/3 ride existing feature work rather than a big
standalone reshuffle. The one thing safe to do standalone now is the
`SidebarMode` fossil fix.
