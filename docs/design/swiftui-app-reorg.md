# SwiftUI App Reorg — Staged Plan

**Milestone:** SwiftUI App Structure & Naming (#104)
**Base branch:** 0.0.2
**Status:** PROPOSAL (read-only plan — no files moved). Grounded in jCodemunch index of HEAD `6f346d9b`.
**Scope:** `fichero/fichero/` (523 `.swift` files: Views 377, Models 72, Services 62, App 7, Intents 3; Resources holds assets, 0 Swift).

> This is a plan for Daniel + future workers. Every move of a `.swift` file in the `Fichero`
> target requires a `project.pbxproj` edit (rule #10). The plan is therefore **staged** so each
> step is small, self-contained, and build-gateable. Do NOT do it all in one branch.

> **Guiding principle (Daniel):** the **front-end (SwiftUI) names are the canonical source of
> truth**. The end goal is one shared namespace across app + engine — and the FIRST step is to
> *settle the SwiftUI vocabulary*, so the backend reorg (#2566/#2569) and API naming (#2565) can
> later be brought **in line with the names the app settles on**. This plan therefore (a) defines the
> canonical FE vocabulary up front, and (b) flags every place the Swift name diverges from the
> engine domain — but it does **not** change any backend name. Backend alignment is a clean
> follow-up that targets the table in §3.

---

## 0. The mechanical constraint that shapes everything

The `Fichero` main target uses **traditional PBX file references**, not synced folders. A `.swift`
file is invisible to the compiler until registered. So a folder reorg is not a Finder drag — every
move = remove the old ref + add the new ref in `project.pbxproj`:

- `ruby scripts/add-swift-file.rb <path>` — register a new/moved-to path
- `ruby scripts/remove-swift-file.rb <path>` — drop the old path
- Never hand-edit `project.pbxproj`.
- The build gate (`scripts/verify_all.sh`, or Xcode `BuildProject`) catches an unregistered or
  stale file as **"Cannot find type …"** — that is the regression signal for each stage.

Consequence: **group moves by folder, one folder per commit, build-gate after each.** A rename of a
file's *contents/type* (no path change) needs NO pbxproj edit and is cheaper than a move — prefer
those where they buy clarity (Stage 1).

Test-target files (`fichero/fichero-tests/`) are the exception — that target uses synced groups, so
moving/renaming test files needs no pbxproj edit.

---

## 1. Current state — where is the soup?

### 1a. `Views/` (377 files) is already ~85% sub-organized
Good, domain-shaped subfolders already exist and are coherent:

`AIProviders/ Actions/ Activity/ Agents/ Automation/ Chat/ Components/ Integrations/`
`KnowledgeGraph/ (+OntologyBrowser/) Library/ (+DocumentInspector/ ImageEditor/ ImageViewer/)`
`MCPServers/ Menu/ MindPalace/ ModelComparison/ Notes/ Onboarding/ Research/ Search/ Settings/`
`Sheets/ Sidebar/ (+Components/ Modes/) Toolbars/ Workflow/ (+NodeConfigs/ WorkflowChainListView/ WorkflowLibraryView/)`

**The actual soup is the loose files at `Views/` root** (not in any subfolder) — 14 files, all
`ContentView`-centric plus two orphans:

| Loose file | Real home |
|---|---|
| `ContentView.swift` (109 symbols) | composition root — keep at root OR new `Views/Content/` |
| `ContentView+Actions.swift` | `Views/Content/` |
| `ContentView+KnowledgeSurface.swift` | `Views/Content/` |
| `ContentView+Navigation.swift` | `Views/Content/` |
| `ContentView+NavigationHistory.swift` | `Views/Content/` |
| `ContentView+Persistence.swift` | `Views/Content/` |
| `ContentView+ReadingLayout.swift` | `Views/Content/` |
| `ContentView+State.swift` (96 symbols) | `Views/Content/` |
| `ContentView+ViewBuilders.swift` | `Views/Content/` |
| `ContentView+WorkflowActions.swift` | `Views/Content/` |
| `ContentViewHelperViews.swift` | `Views/Content/` |
| `ContentViewModifiers.swift` | `Views/Content/` |
| `DocumentTabView.swift` | `Views/Library/` (it's the reader tab host) |
| `OpenAffordances.swift` | `Views/Content/` or a `Views/Navigation/` shared folder |

### 1b. Minor structural smells
- `Views/ModelComparison/` and `Views/Chat/ComparisonDetailView*` + `Views/Chat/ChatMapGrid` —
  model-comparison UI is split across two folders (`Chat/` and `ModelComparison/`). Candidate merge.
- `Views/Components/` is a genuine grab-bag (web view, flow layout, status badge, schedule/trigger
  rows, workflow rows). The schedule/trigger/workflow rows arguably belong with `Automation/` /
  `Workflow/`; leave the truly-generic primitives (FlowLayout, StatusBadge, SplittablePane,
  MacPlainTextEditor, FicheroWebView, LibraryImageView, ProviderLogoView) in `Components/`.
- `Views/Sidebar/ActivityDataProcessing.swift` + `Views/Sidebar/Modes/ActivityRun.swift` —
  Activity logic living under Sidebar; the `Activity/` folder is the natural owner.

### 1c. `Models/` (72 files) — two things are mixed in one folder
`Models/` holds BOTH plain data DTOs (`Document`, `Artifact`, `Note`, `Run`, `Event`,
`SpatialModels`, `WorkflowTypes`, …) AND `@Observable` domain **stores** (`DocumentStore`,
`EntityStore`, `ClaimStore`, `ArtifactStore`, `NoteStore`, `ResearchStore`, `SearchStore`,
`WorkflowStore`, `CanvasItemStore`, `CanvasLayoutStore`, `AuditStore`, `BackupStore`,
`ActionStore`, …) and Sidebar plumbing (`SidebarItem*`, `SidebarState`, `SidebarSearchTypes`).
Per the "Observable data layer" memo the stores are the canonical endpoint accessors — they deserve
their own `Models/Stores/` (or top-level `Stores/`) split from pure `Models/`.

### 1d. `Services/` (62 files) — flat, but coherent by suffix
One flat folder. Two implicit kinds already distinguishable by name:
- Hand-written wrappers around the OpenAPI client, suffix `*Generated.swift` (e.g.
  `ArtifactServiceGenerated`, `WorkflowServiceGenerated`, `DocumentServiceGenerated`) — despite the
  suffix these are **editable** (CLAUDE rule #3).
- Plain services / type bags (`APIClient`, `APIEndpoints`, `EngineConfig`, `*Types.swift`,
  `AppleScript*`, `EmbeddedBackendService`, `RemoteClientPairing`, `WorkflowStream*`).

Not urgent to subfolder, but if grouped, align to the engine's route domains (see §3).

---

## 2. Target organization

### Views — domain/surface folders (mostly already present)
Keep the existing surface folders. The only structural change is **draining the loose root** into a
new `Views/Content/` group, plus a few targeted moves:

```
Views/
  Content/         ← NEW: all ContentView*, ContentViewModifiers, ContentViewHelperViews, OpenAffordances
  Library/         ← + DocumentTabView (from root)
  Activity/        ← + ActivityDataProcessing, Modes/ActivityRun (from Sidebar/)
  Spatial/         ← RENAMED from MindPalace/ (see §4)
  ModelComparison/ ← absorb Chat/ComparisonDetailView*, Chat/ChatMapGrid (optional, Stage 4)
  AIProviders/ Actions/ Agents/ Automation/ Chat/ Components/ Integrations/
  KnowledgeGraph/ MCPServers/ Menu/ Notes/ Onboarding/ Research/ Search/
  Settings/ Sheets/ Sidebar/ Toolbars/ Workflow/   (unchanged)
```

### Models — split data from stores
```
Models/
  Stores/    ← NEW: *Store.swift (Observable domain stores) + ObservableDomainStore.swift
  (root)     ← pure DTOs / value types: Document, Artifact, Note, Run, Event, SpatialModels*, Workflow*, ...
  Platform/  ← unchanged
  Sidebar*   ← optionally a Models/Sidebar/ group (SidebarItem*, SidebarState, Sidebar*Types)
```

### Services — optional domain grouping (low priority)
If subfoldered later, mirror engine route domains: `Services/Knowledge/`, `Services/Workflow/`,
`Services/Library/`, `Services/Activity/`, `Services/AI/`, `Services/Core/` (APIClient,
EngineConfig, error). Defer — it's the least-soupy folder. The naming win here is **renaming
`Services/MindPalaceLibraryProjector.swift` → `SpatialLibraryProjector.swift`** (§4).

---

## 3. Canonical front-end vocabulary (settle THIS first; backend follows)

Per the guiding principle, this table is the deliverable the engine reorg (#2566/#2569) and API
naming (#2565) will later target. **The "Canonical Swift name" column is the source of truth.** The
"Engine today" column records the current backend name so the divergence is visible; the "Aligned?"
column flags what the backend should rename to match (a follow-up — NOT done here).

| Surface / domain | Canonical Swift view folder | Canonical Swift store | Canonical Swift service | Engine domain today (route/model) | Aligned? |
|---|---|---|---|---|---|
| Library / documents | `Views/Library/` | `DocumentStore`, `ArtifactStore` | `DocumentServiceGenerated`, `ArtifactServiceGenerated` | `/api/documents`, `/api/artifacts` | ✅ |
| Knowledge graph | `Views/KnowledgeGraph/` | `EntityStore`, `ClaimStore`, `InterpretationStore` | (KG calls via APIEndpoints) | `/api/entities`, `/api/claims` | ✅ |
| **Spatial canvas** | **`Views/Spatial/`** (rename from `MindPalace/`) | `CanvasItemStore`, `CanvasLayoutStore` | **`SpatialLibraryProjector`** (rename from `MindPalaceLibraryProjector`) | `api/routes/mind_palace.py`, `/api/mindpalace/…`; models already `spatial_models.py` (`Spatial*`) | ❌ **route/module still `mind_palace`** → BE should rename to `spatial` (#2565) |
| Workflow | `Views/Workflow/` | `WorkflowStore`, `WorkflowExecutionStore` | `WorkflowServiceGenerated`, `WorkflowStreamService` | `/api/workflows` | ✅ |
| Activity / runs | `Views/Activity/` | (Run / Trace models) | `ActivityServiceGenerated` | `/api/activity` | ✅ |
| Research | `Views/Research/` | `ResearchStore` | `ResearchService` | `/api/research` | ✅ |
| Search | `Views/Search/` | `SearchStore`, `SavedSearchService` | `SearchServiceGenerated`, `SavedSearchServiceGenerated` | `/api/search` | ✅ |
| Notes | `Views/Notes/` | `NoteStore` | `NoteService` | `/api/notes` | ✅ |
| Chat | `Views/Chat/` | (SidebarChat types) | `ChatServiceGenerated`, `ConversationServiceGenerated` | `/api/chat`, `/api/conversations` | ✅ |
| Model comparison | `Views/ModelComparison/` | — | `ModelComparisonService` | (compare endpoints) | ✅ |
| AI providers / models | `Views/AIProviders/`, `Views/Settings/` | — | `ProviderServiceGenerated`, `ModelServiceGenerated`, `LocalModels…` | `/api/providers`, `/api/models` | ✅ |
| Automation (schedules/triggers) | `Views/Automation/` | — | `AutomationServiceGenerated` | `/api/automation` | ✅ |
| Actions (audited action layer) | `Views/Actions/` | `ActionStore`, `AuditStore` | `ActionInvokeService`, `ActionLibraryService` | `/api/actions`, audit | ✅ |
| Import / intake | (in Library/Sheets) | — | `ImportServiceGenerated` | `/api/import` | ✅ |
| Image editing/viewing | `Views/Library/ImageEditor`, `ImageViewer` | `ImageEditorModel` | `ImageEditingServiceGenerated` | `/api/image…` | ✅ |
| Integrations | `Views/Integrations/` | — | `IntegrationsService` | `/api/integrations` | ✅ |
| MCP servers | `Views/MCPServers/` | `MCPServer` | `MCPService` | `/api/mcp` | ✅ |
| Storage / backups | `Views/Settings/` | `BackupStore` | `StorageServiceGenerated` | `/api/storage`, `/api/backups` | ✅ |
| Composition root | `Views/Content/` (NEW) | `AppState` | — | n/a (client shell) | n/a |
| Sidebar shell | `Views/Sidebar/` | `SidebarState` | — | n/a (client shell) | n/a |

**Only one real divergence exists: `MindPalace`/`mind_palace` vs `Spatial`.** Everything else is
already aligned (or is a client-only shell concept with no backend counterpart — that's fine, not a
divergence). The Swift `*Store` layer is intentionally client-side and has no engine mirror by
design. So "settling the FE vocabulary" reduces to: **finish the Spatial rename in the app (Stage 1),
then hand #2565 the one row that says ❌.**

### Engine half (record only — do NOT touch in this milestone)
The engine is already half-migrated: `spatial_models.py` exists with `Spatial*` types, but the route
module/prefix is still `mind_palace` / `/api/mindpalace`. The generated Swift calls inherit that:
`CanvasItemStore`/`CanvasLayoutStore` call `…ApiMindPalaceFoldersFolderIdCanvasItems…`. After the
app settles on `Spatial`, #2565 renames `api/routes/mind_palace.py → spatial.py` and
`/api/mindpalace → /api/spatial`, regenerates OpenAPI, and the generated call names follow.

---

## 4. MindPalace → Spatial verdict

**Verdict: RENAME `Views/MindPalace/` → `Views/Spatial/` (and the `MindPalace*` symbols →
`Spatial*`). Do NOT delete the folder — its files are LIVE.**

The retired feature (#1455/#1569) was the *rooms / mind-palace 3D-room* product framing. What
physically survived under `Views/MindPalace/` is the **live spatial-library canvas**, wired into the
real Library:

- `SpatialScene3D` (RealityKit 3D canvas) is rendered by `Views/Library/LibraryView.swift:245` and
  `Views/Library/DocumentKGSurface.swift:264`.
- `Spatial2DCanvas` (the type inside the confusingly-named `SpatialView.swift`) is rendered by
  `LibraryView.swift:255` and `SpatialScene3D.swift:250`.
- `MindPalaceLibraryProjector.project(...)` is called from `LibraryView.swift:619` to build the
  nodes/links the canvas draws.

So this folder is **live-but-misnamed**, exactly the case the milestone flagged.

Suggested symbol renames (contents-only where possible → no pbxproj churn):
`MindPalaceLibraryProjector → SpatialLibraryProjector`, `MindPalaceLibraryInput/Projection →
SpatialLibraryInput/Projection`, `MindPalaceNode → SpatialNode`, `MindPalaceNodeType →
SpatialNodeType`, `MindPalaceLink → SpatialLink`, `MindPalaceConnection(Type) →
SpatialConnection(Type)`, `MindPalaceTheme → SpatialTheme`, `MindPalaceNodeThumbnail →
SpatialNodeThumbnail`, `MindPalaceTextureCache → SpatialTextureCache`. File renames:
`SpatialView.swift` (it actually houses `Spatial2DCanvas`) → consider `Spatial2DCanvas.swift`;
`Models/MindPalaceTheme.swift → Models/SpatialTheme.swift`;
`Services/MindPalaceLibraryProjector.swift → Services/SpatialLibraryProjector.swift`.

**Coordinate the engine half with #2565** (see §3) — but the app rename does **not** wait on it; the
generated `…ApiMindPalace…` call names are machine-generated and follow the schema later.

---

## 5. Cruft / dead code

There are **no genuinely-dead *files*** under `Views/MindPalace/` — every file is reachable from
`LibraryView`/`DocumentKGSurface` (verified via `check_references`). The cruft is at the **symbol**
level: the retired "rooms" concept left a few types behind that nothing renders.

### Confirmed dead (0 production refs; only appears in `scripts/.test_coverage_baseline.json`)
| Symbol | Declared in | Evidence |
|---|---|---|
| `MindPalaceRoom` (struct) | `Models/SpatialModels.swift:96` | `check_references` + regex sweep: zero refs in `fichero/fichero/**` and zero in `fichero-tests/**`; only the coverage-baseline JSON lists it. The "room" container is the retired concept; the live canvas works off nodes/links, not rooms. |

### Verify-before-delete (likely dead room-scoped residue — confirm with `find_references` at delete time)
- `RoomSceneSummary` / `SpatialRoom` mirrors referenced only in a `SpatialModels.swift` doc-comment
  (line 6) — check whether any store decodes them.
- `MindPalaceConnection` / `MindPalaceConnectionType` — used by `SpatialModels+Links.swift`; confirm
  a live decoder path exists (the *projector* builds `MindPalaceLink`, not `MindPalaceConnection`).
  If only the projector path is live, the room-level `Connection` types may be prunable too.

> Do NOT mass-delete on this list — `MindPalaceRoom` is the one safe, isolated delete. The others
> need a fresh `find_references` at execution time (the index can lag; verify against disk).

### Index hygiene note (not a code problem)
The `check_references`/`search_text` results surfaced sibling worktrees under
`.claude/worktrees/agent-*/` (e.g. `agent-a6ca55fc…`, `agent-a21590fc…`) as duplicate hits for
`LibraryView.swift` etc. Those are stale agent worktrees in the index, not extra code — ignore them
when counting references (always trust the `fichero/fichero/**` path, not `.claude/worktrees/**`).

---

## 6. Staged execution plan (each stage = one commit, build-gated)

**Stage 1 — Settle the canonical Spatial vocabulary + kill the one dead symbol (CHEAPEST, HIGHEST
CLARITY). Do first.** This is the concrete act of "settle the front-end names": it resolves the only
FE↔BE divergence in §3 on the app side, so the backend has a fixed target. Self-contained,
mostly contents-only edits.
1. Delete `MindPalaceRoom` struct from `Models/SpatialModels.swift` (re-verify 0 refs first).
2. Rename the `MindPalace*` Swift **types** → `Spatial*` (find/replace across
   `Models/SpatialModels*.swift`, `Models/MindPalaceTheme.swift`, `Services/MindPalaceLibraryProjector.swift`,
   `Views/MindPalace/*.swift`, and call sites in `Views/Library/LibraryView.swift`,
   `DocumentKGSurface.swift`, `CanvasItemStore.swift` comments, tests). Contents-only → no pbxproj.
3. Rename files: `Models/MindPalaceTheme.swift → SpatialTheme.swift`,
   `Services/MindPalaceLibraryProjector.swift → SpatialLibraryProjector.swift`,
   `Views/MindPalace/SpatialView.swift → Spatial2DCanvas.swift`. Each file rename =
   `remove-swift-file.rb` old + `add-swift-file.rb` new.
4. Rename folder `Views/MindPalace/ → Views/Spatial/` (re-register both files at new paths).
5. Update `scripts/.test_coverage_baseline.json`, `scripts/check_appkit_imports.py`,
   `scripts/check_observer_pattern.py`, `scripts/check_openapi_shadow_types.py` paths/symbols.
6. Rename test files (`MindPalace*Tests.swift`) — test target is synced, no pbxproj edit.
7. Build-gate. Commit. (Engine route rename → handed to #2565 as a follow-up; not in this milestone.)

**Stage 2 — drain the loose `Views/` root into `Views/Content/`.**
One folder, ~14 file moves, each a pbxproj re-register. Pure move, no logic change → build is the
only gate needed. Keep `ContentView.swift` itself wherever the team prefers (root or `Content/`).
Move `DocumentTabView.swift → Views/Library/` in the same commit.

**Stage 3 — Models split: `Models/Stores/`.**
Move every `*Store.swift` + `ObservableDomainStore.swift` into `Models/Stores/`. ~20 moves, pbxproj
re-register each. No symbol renames. Build-gate.

**Stage 4 — small consolidations (optional, lowest priority).**
- Move `Views/Sidebar/ActivityDataProcessing.swift` + `Sidebar/Modes/ActivityRun.swift` → `Views/Activity/`.
- Merge `Views/Chat/ComparisonDetailView*` + `ChatMapGrid` into `Views/ModelComparison/` (or vice-versa).
- Tidy `Views/Components/` grab-bag (schedule/trigger/workflow rows → their domain folders).
Each as its own tiny commit + build-gate.

**Stage 5 — engine alignment (separate milestone, follows the FE names; #2565/#2566/#2569).**
Backend renames to match §3: `api/routes/mind_palace.py → spatial.py`, `/api/mindpalace → /api/spatial`,
regenerate OpenAPI, let the generated `CanvasItem/CanvasLayout` call names update. Out of scope for
#104 — listed so the alignment hand-off is explicit.

---

## 7. Recommended first move

**Stage 1.** It is the cheapest and highest-clarity change AND it is the literal first step of the
guiding principle — *settle the front-end names so the backend can follow*. It's self-contained (the
Spatial files only touch Library + a projector + a theme), mostly contents-only find/replace (little
pbxproj churn), it kills the single confirmed dead symbol (`MindPalaceRoom`), and it removes the most
confusing name in the app (a *retired* feature's name sitting on *live* code) — resolving the only ❌
row in the §3 vocabulary table. It de-risks every later stage by fixing the vocabulary first.
