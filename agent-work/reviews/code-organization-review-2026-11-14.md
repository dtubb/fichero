# Code organisation review — 2026-11-14

Tree reviewed: `code-org` at `7438dd2f5d` (origin/integration). Rules: `docs/contributor_manual/specs/harness/code-organization.md`.
Method: stdlib scans over the two trees (file counts per folder, line counts, top-level type declarations per Swift file,
word-boundary reference search for every dead candidate), the repo's own guards in `--list` mode, jcodemunch
`find_dead_code` (advisory: its index was stale, confidence capped at 0.6, so no file was called dead on its word alone).
No code was changed. Issue numbers are the existing families; the manager files the lanes.

How Swift moves are done: `fichero/fichero` is a synchronized root (AGENTS.md rule 10), so a `git mv` inside it needs no
project edit; `scripts/check_xcode_registration.py` proves it after. `scripts/add-swift-file.rb` / `remove-swift-file.rb`
are for a file the project lists explicitly (a `membershipExceptions` entry, a test target); `project.pbxproj` is never
hand-edited. Python moves repoint every importer in the same commit; no alias module stays (AGENTS.md rule 0).

## Top findings, ranked by value

| # | Finding | Evidence | Fix | Batch |
|---|---|---|---|---|
| 1 | 18 shim modules under `api/routes/` (`kg_*.py`, `folders.py`, `search_explain.py`): a docstring "Moved to … (#2569)", a `from … import *` and a `sys.modules` alias | `grep -l "sys.modules\[__name__\]"` → 18 files; `api/main.py` imports 17 of them; 31 other files import the shims | delete the 18, repoint `main.py` and the 31 importers at `api/routes/kg/*`, `api/routes/document/folders`, `api/routes/search/explain` | P1 |
| 2 | `Models/` 355 and `Services/` 220 Swift files flat in one folder each | `check_folder_organization --list`; both allowlisted since #1944 at 53 and 60 files, now 6× and 4× that | one subfolder per feature prefix (Models: Segment 22, Workflow 20, Recipe 17, Document 15, Activity 15, Library 11, Inspector 11, Sidebar 10; Services: Workflow 13, Pairing 12, Entity 12, Activity 11, Engine 10, Annotation 10, Action 10, Research 9); tests mirror | S1–S4 |
| 3 | Dead workflow UI: `Views/Workflow/Library/WorkflowChainListView.swift` + its `WorkflowChainListViewParts/` (6 files), `Views/Workflow/Execution/WorkflowExecutionView.swift` (5 types), `Views/Workflow/Editor/SimpleWorkflowView.swift` | zero references from `fichero/fichero` outside the set; `WorkflowChainListView` named only by `WorkflowArchitectureBoundaryTests.swift`; `check_dead_files` has carried the first since 2026-08-10 "do not let this entry outlive the decision" | `git rm` 9 files, drop the boundary test's mention, drop 3 `KNOWN_VIOLATIONS` entries | S5 |
| 4 | Six production types reached only from `fichero/Tests`: `Models/CacheModel.swift`, `Models/DragDropModel.swift`, `Views/Settings/MCP/MCPServersSheet.swift`, `App/IntegrationsPlaceholderSheet.swift`, `Views/Preview/PDFViewer/PageImageGrid.swift`, `Intents/FicheroShortcuts.swift` (none) | word-boundary grep: each name appears in its own file and one test file only | delete the type and its test together (`CacheModelTests`, `DragDropTests`, `PageImageGridTests`, the two `AboutSettingsSurfaceTests` assertions); owner question 3 | S5 |
| 5 | Loose engine modules at the package root: 18 beyond `__init__`/`__main__` | `ls src/fichero_server/*.py` | homes below (P2) | P2 |
| 6 | Python test folders that mirror no package: `tests/unit/jobs/` (119 files, imports `execution` 132×), `kg/` (27, `knowledge` + `api/routes/kg`), `transport/` (29, `security` + `api`), `export/` (12, tests `export_service.py`), `check/`, `harness/`, `seams/`, `activity/`, `packaging/` | import counts per dir | `git mv` to `tests/unit/execution/`, `knowledge/`, `security/`, `export/` (after P2 creates `export/`); `check/`→`checking/`, `harness/`→`workflows/` or `fichero-builder/tests/` | P3 |
| 7 | Oversized Swift: `Views/Library/ViewModes/Canvas/3D/SpaceSceneView.swift` 1,169 lines under `swiftlint:disable file_length`; `Views/Shell/ContentView/ContentView.swift` 998 (2 under the shell cap); `Services/DocumentService.swift` 960; `FicheroApp.swift` 950; `Models/RecipeSetupStore.swift` 895 | `wc -l` | split by concern into `+Topic` extensions (`SpaceSceneView+Camera`, `+Gestures`, `+Nodes`; `ContentView+…` already has 25 siblings, so move the next concern out before it grows) | S6 |
| 8 | Oversized Python: `db/__init__.py` 8,503; `workflows/tools/vision_base.py` 6,430; `api/routes/document/segments.py` 6,150; `execution/jobs.py` 5,554; `llm/__init__.py` 5,119; `api/routes/document/documents.py` 4,840; `api/main.py` 3,146 (84 non-generated modules over 1,000) | `wc -l` | package `__init__` files become re-export doors over `db/core.py`, `llm/core.py`; the route modules split into a package per resource (`segments/readings.py`, `segments/conversion.py` already exist as siblings, fold the rest); `main.py` keeps wiring only | P4 (one module per lane) |
| 9 | `Views/Components/` 28 loose + 9 in `BackendConnection/`: feature files among primitives | listing | move `SegmentAttributeMenu`, `SegmentVerbMenu`, `SourceDirectionMenu` → `Views/Segments/`; `ReadingOrderList(+Unordered)`, `ReadingOrderPicker` → `Views/Reader/`; `NodeClassPicker` → `Views/Inspector/Knowledge/`; `ProviderLogoView` → `Views/Settings/AI/`; `LibraryAccessDeniedView`, `LibraryImageView` → `Views/Library/`; `BackendConnection/`, `BackendRootGate` → `Views/Connect/`; keep `FlowLayout`, `MarkdownText`, `StatusBadge`, `SplittablePane`, `SkeletonPlaceholder`, `RubberBand`, `FrameAnimation`, `MiniToolbar*`, `PaneFilter*`, `DragPreviewLabel`, `MacPlainTextEditor`, `FicheroWebView`, `CommandScrollZoom`, `LiveUpdatesPausedPill`, `UndoRefusalNotice` | S7 |
| 10 | `Views/Library/` root: 49 loose files, 19 of them `LibraryView(+…)` which belong, 30 that do not | listing | `Thumbnail*`, `LibraryThumbnail*`, `TextPreviewThumbnail`, `ThumbnailPrefetchLedger`, `EntityThumbnailView` → `Library/Thumbnails/`; `LibraryOutline*` → `Library/Outline/`; `IIIFImport`, `LocateOriginals`, `ProjectTransferSheet`, `SyncedHostAskSheet`, `DocumentPickerSheet` → `Library/Sheets/`; `BlankProposalsLine`, `HiddenPagesLine`, `ShowThroughOnlyLine`, `ProposedDocumentsInItems` → `Library/Notices/`; `*PreviewCatalog` → `Library/Previews/`; `TrashPane` → `Sidebar/Trash/` | S7 |

### Generated-code warnings (owner's addition, 2026-11-14)

The owner's incremental iMac build showed 7 Swift warnings, 4 of them in the generated `Types.swift` of the
`fichero-api-client` package: 3× `public import of 'Foundation' was not used in public declarations or inlinable code
[#UnusedImportAccess]`, 1× the same for `OpenAPIRuntime`.

Cause, verified against the generator checkout and plugin output in a local DerivedData:
- swift-openapi-generator 1.13.0 (PR #883, "add access modifiers to generated imports") writes the same seven-line header
  into every generated file when `accessModifier: public`: `@_spi(Generated) public import OpenAPIRuntime` and
  `public import struct Foundation.URL/.Data/.Date` (twice, for Linux and not). Since 1.13 the output is split into nine
  files (`Types.swift`, `Types+Components*.swift` ×6, `Types+Operations.swift`, `Client.swift`). `Types.swift` now holds
  only `APIProtocol`, its convenience extension and `enum Servers`: zero uses of `Date`, `Data`, `URL` or any
  `OpenAPIRuntime.` symbol in a public declaration, so the compiler flags all four imports. The five near-empty
  `Types+Components*.swift` placeholders and `Client.swift` (`Date`, `Data` unused) carry the same imports, so a CLEAN build
  shows more than the incremental 7.
- Upstream: issue #968 (duplicate of #946), fix pending in PR #947, which wraps the imports in Swift 6.4 warning
  suppression rather than pruning them. Reported workaround: stay below 1.13.0.
- Version drift: the repo's `Package.resolved` pins the generator at 1.10.3 and the runtime at 1.9.0, so the builder
  (`-disableAutomaticPackageResolution`) never builds these warnings; `Package.swift` says `from: "1.6.0"`, and every
  DerivedData on the owner's machines resolved 1.13.1. The owner's Xcode and the builder compile different generated code.

Which fix applies: the **generator package version**, not the config, not a target setting, not the schema.
- Config (`openapi-generator-config.yaml`): `accessModifier: public` is required (the app imports the module); `package`
  or `internal` would break the build, and no key turns the import access modifiers off.
- Target settings: `SWIFT_UPCOMING_FEATURE_MEMBER_IMPORT_VISIBILITY=YES` is on the app target only and unrelated; the
  diagnostic group `UnusedImportAccess` can be raised to an error with SE-0443 but not suppressed per group before Swift 6.4.
- Schema: `Types+Components+Schemas.swift` uses `Date` 412 times (171 `date-time` fields); the warning is per file, so the
  schema cannot "use" the import in the protocol file.
- Fix: cap `Package.swift` to `.package(url: …swift-openapi-generator, "1.6.0"..<"1.13.0")` and keep `Package.resolved` at
  1.10.3 (or move to 1.12.2, the last warning-free release) so the owner's Xcode resolves what the builder builds; lift the
  cap when PR #947 ships and re-baseline in the same commit. No generated file is touched.
- Until then, if the owner wants 1.13.x for other reasons: four baseline entries in the generated bucket, each
  "upstream apple/swift-openapi-generator#968, fix #947", dropped when the cap lifts.

## Findings by group

### 1. Misplaced files and folders

Swift
- `App/IntegrationsPlaceholderSheet.swift`, `App/NewLibraryPanel.swift`, `App/LibraryWindow(+Actions).swift`: View types in
  the lifecycle folder. `IntegrationsPlaceholderSheet` is also dead (finding 4). `NewLibraryPanel` → `Views/Onboarding/FirstRun/`;
  `LibraryWindow` is a `Scene`, allowed in `App/` (name it so in the spec's layer list).
- `Views/Models/` (2 files: `ModelFinderView`, `CandidateFitLabel`): a folder named for a layer; both are used by
  `Views/Onboarding/` → move there as `Views/Onboarding/ModelFinder/`.
- `Views/Prototypes/` (2 files): `PrototypeEditorSheet` is opened from `Sidebar/Sections/LibraryHeaderRow` and
  `Inspector/Source/Info` → `Views/Inspector/Project/` (prototypes are a project's node kinds).
- `Views/SPARQLConsole/` (1 file), `Views/Auth/` (1 file): single-file folders → `Views/Library/ViewModes/Graph/` and
  `Views/Settings/Sharing/Access/`.
- `Views/LooveCoverage/` (3 files, 602-line view): a model-coverage report opened from `FicheroApp.swift`; it is a Settings
  or Activity surface, not a top-level feature → `Views/Settings/AI/Coverage/`.
- `Views/Shell/` root 17 loose files: `PaneContentPlan`, `PaneEmptyState`, `PaneScopedOption`, `PaneSurface`,
  `PaneVisibility` → `Shell/PaneHead/` or a `Shell/Panes/`; the three `*Notice`/`*Alert` files → `Shell/Alert/` (exists, 1 file).
- `Views/Preview/` root 15 loose: `EditorView(+PDFPages)` (the image editor's root) → `Preview/ImageEditor/`; the five
  `Folder*Preview`/`PreviewFolderView*` files → `Preview/Folder/`.
- `Views/Shell/ContentView/` 35 and `Shell/Toolbar/` 33 (both allowlisted at 20): the `WorkflowBar*` family (17 files)
  → `Shell/Toolbar/WorkflowBar/`; `ContentView+State*` (5) and `ContentView+Search*` (3) → `ContentView/State/`,
  `ContentView/Search/`; `Sidebar*Observer/Routing/Scope` (4) → `Shell/ContentView/Sidebar/`.
- 38 observable types under `Views/` (`Focused*` ×6, `DatasetModeStore`, `WindowWorkspaceStore`, `AgentConsentStore`,
  `ServerSettingsModel`, `LibraryOutlineModel`, `LibraryToolbarState`, `SidebarStateManagers`…): allowed beside their
  views if one feature reads them (owner question 1). `WindowWorkspaceStore` and `AgentConsentStore` are read from
  `App/` too → `Models/Window/`, `Models/Sharing/`.
- Test mirror gaps: `Views/Capture`, `Views/Segments`, `Views/LooveCoverage`, `Views/Models`, `Views/Prototypes`,
  `Views/SPARQLConsole` have no `Tests/Unit/general/Views/<Feature>/`; the 437 files in `Tests/Unit/general/Models/` follow
  the `Models/` split.

Python
- Package-root modules and their homes: `export_service.py` (24 importers), `page_export.py` (23), `kept_export.py` (5),
  `catalogue_sheet.py` (1) → new `export/` package (the test dir `tests/unit/export/` already exists); `histdate.py` (16),
  `feast_days.py` (2) → `knowledge/dates/` or `core/`; `bookmarks.py` (14) → `models/` + `db/`; `tool_context.py` (14) →
  `workflows/tools/`; `sync_folder.py` (2) → `importers/`; `sharing_host_file.py` (0 engine importers besides
  `api/routes/auth/authz.py`) → `security/`; `startup_warnings.py` → `core/`; `image_op_job.py`, `_pdfium_probe.py` →
  `media/`; `canvas_picture.py`, `spatial_arrange.py` → `models/canvas` side package `canvas/`; `split_carry.py` →
  `recipes/`; `verification_targets.py` (1 test) → `checking/`; `errors.py` (6) stays by the 2026-07 survey's advice or
  → `core/errors.py` with the same commit repointing 6 files.
- `api/routes/` root: besides the 18 shims, `check.py`, `evaluation.py`, `find_documents.py`, `reading_at_scale.py`,
  `sync_folders.py`, `training.py`, `workers.py` are real route modules with no resource folder → `api/routes/<resource>/`
  (`training/` for `training`+`evaluation`, `system/` for `workers`, `document/` for `find_documents`+`sync_folders`+
  `reading_at_scale`, `check.py` → `checking/`).
- `api/` root: `uds_*.py`, `tcp_transport.py`, `transport_diagnostics.py`, `client_presence.py` (6 files) → `api/transport/`.
- 128 route modules declare Pydantic models (`system/recipes.py` 115 classes, `document/documents.py` 61,
  `document/segments.py` 54): request and response shapes belong in `models/<resource>.py`; the OpenAPI guards
  (`check_schema_names_are_unique`, `check_openapi_shadow_types`) keep the names stable through the move. Large; one
  resource per lane, rides with P4.
- `agent-work/design/engine-package-reorg.md` proposes shims for every move; AGENTS.md rule 0 forbids them. The doc is
  superseded on that point (the spec says so); its domain map stays useful.

Repo root
- Present and sound but missing from AGENTS.md's list: `CLA.md`, `CODE_OF_CONDUCT.md`, `LICENSE`, `LICENSING.md`,
  `NOTICE`, `harness.toml`, `ruff.toml`, `requirements-docs.txt`, `.python-version`, `icons/`, `web/`, `pipeline/`,
  `agents/`, `test-fixtures/`. The spec's root allowlist names them; AGENTS.md should match in the same lane.
- The integration checkout (not this worktree) carries untracked root dirs `.agents/`, `briefs/`, `ssh_m4_dummy/`,
  `.venv.thin-2026-10-09/`, `.metadata_never_index`: gitignore or remove; a root guard would flag them.

### 2. Dead code (each verified by word-boundary search over `fichero/` and `fichero-server/`)

- Zero references anywhere: `Views/Workflow/Editor/SimpleWorkflowView.swift`, `Views/Workflow/Execution/WorkflowExecutionView.swift`
  (with `ThreadRow`, `ThreadDetailSheet`, `ThreadDetailContent`, `DetailRow`), `Intents/FicheroShortcuts.swift`,
  `Views/Preview/ImageViewer/ScrollWheelZoom.swift` (its four types used only inside the file),
  `fichero-server/src/fichero_server/media/image_prep_samples.py`.
- Reached only by the dead set: `Views/Workflow/Library/WorkflowChainListView.swift` (+ `WorkflowChainListViewParts/` ×6;
  `ChainDetailContent` is also used by `Workflow/Editor/ChainEditorView.swift`, so that one file moves to `Editor/` instead).
- Reached only by tests: `CacheModel`, `DragDropModel`, `MCPServersSheet`, `IntegrationsPlaceholderSheet`, `PageImageGrid`
  (finding 4).
- `check_dead_files` false positives to drop from `KNOWN_VIOLATIONS` once periphery replaces the heuristic:
  `PreviewMarkupToolsRow+Shapes`, `AISettingsView+Tabs`, `ContentView+WindowEnvironment`, `EntrySourcePreview`,
  `ActivityDataProcessing`, `LibraryView+EntityFiltering`, `LibraryView+ListView`, `EntityDetailView+Biography`,
  `ChatInspector+ScopedDocuments`, `WorkflowEdgeView+Edges` (extension files with a private helper type).
- Not dead, despite the 2026-07 survey: `CollectionWorkspaceStub.swift` no longer exists; `LooveCoverageView` and
  `SPARQLConsoleView` are reached from `FicheroApp.swift`; `PrototypeEditorSheet`, `ModelFinderView`, `CandidateFitLabel`
  are reached from three or four views each.
- Comment hygiene: both guards green; `swiftlint:disable` appears in 25 places (4× `file_length`, 4× `cyclomatic_complexity`);
  755 `# noqa` and 70 `# type: ignore` in the engine, mostly `E402` on deferred imports. Not dead code, but the
  suppressions are the warning class the compiler and pyright ratchets would make visible.

### 3. Bad or inconsistent names

- 135 Swift files named for none of their top-level types; 303 declare more than two. Worst: `App/Menus/FocusedCommands/
  FocusedCommandButtons+FocusedValues.swift` (26 types), `Models/ResearchModels.swift` (17), `Models/WorkflowChain.swift` (15),
  `App/Menus/ViewMenuPaneSections.swift` (15), `Services/ProviderServiceTypes.swift` (14). The `*Types.swift` wire bundles
  (19 files) are the owner's call (question 2); the `FocusedCommandButtons+*.swift` files declare 9–26 button types each
  under an extension name and should be `App/Menus/FocusedCommands/<Verb>/` folders of one-type files.
- 33 View-conforming types outside `Views/`: 30 are menu command views under `App/Menus/` (allowed by the spec);
  `IntegrationsPlaceholderSheet`, `NewLibraryPanel`, `LibraryWindow` are the three to move or delete.
- Platform suffix: 13 files end `IOS`, 2 end `iOS` (`DocumentKGWebPaneCoordinatoriOS.swift`,
  `FullScreenImagePreviewIOSOnly.swift` mixes both), 1 ends `MacOS` → rename the two outliers to the majority (question 4).
- `Views/Models/` collides with `Models/`; `Views/Workflow/Library/` collides with `Views/Library/` (it is the workflow
  picker) → `Views/Workflow/Picker/`.
- Python tests: 553 of 2,434 carry the `_NNNN` suffix; one uses a prefix (`tests/unit/api/test_6085_one_listing.py`) → rename.
  Duplicate stems across packages (`accounts.py`, `authz.py` in `security/` and `api/routes/auth/`; `graph.py`,
  `search.py`, `entities.py` in `knowledge/` and `api/routes/`) are allowed by the spec (package path disambiguates) but
  `api/routes/auth/authz.py` vs `security/authz.py` deserves a rename of the route module to `access.py`.
- Guard data names: `swiftlint_warning_baseline.json`, `release_size_baseline.json`, `perf_trial_baseline.json`,
  `stall_baseline.json`, `ambient_owner_in_tests_baseline.json`, `*_allowlist.json` (5): consistent already; new ratchets
  follow `<tool>_<what>_baseline.json`.

### 4. Catch-all folders

| Folder | Files | Rule | Status |
|---|---|---|---|
| `Models/` | 355 flat (+ `Platform/`, `Selection/`) | 18 | allowlisted since 53 |
| `Services/` | 220 flat (+ 3 subfolders) | 18 | allowlisted since 60 |
| `Views/Library/` | 49 flat | 18 + mixed-concern | allowlisted since 42 |
| `Views/Shell/ContentView/` | 35 | 18 | allowlisted at 20 |
| `Views/Shell/Toolbar/` | 33 | 18 | allowlisted at 20 |
| `Views/Components/` | 28 | 18 | allowlisted at 19 |
| `Views/Sidebar/ItemRow/` | 22 | 18 | allowlisted at 20 |
| `App/Menus/` | 18 (+ `FocusedCommands/` 14 + `ItemVerbs/` 7) | 18 | at the line |
| `fichero_server/` root | 20 modules | 2 | no guard |
| `api/routes/` root | 26 modules, 18 shims | 0 loose | no guard |
| `fichero_server/core/` | 23 modules | utilities only | sound; `egress.py`, `tls.py`, `no_model_in_get.py` are domain code → `security/`, `api/` |
| `tests/unit/` root | 24 test files | mirror | `test_perf_*`, `test_memory_ratchet`, `test_query_ratchet_*` → `tests/perf/` or `tests/unit/core/` |
| `scripts/` | 256 entries flat | tooling | 122 guards + 134 others in one folder; a `scripts/release/`, `scripts/harness/` split is cosmetic, low value |

Every allowlisted folder has grown since its entry: the allowlist records a count, the guard checks presence, so the
entries never ratchet. Spec `code-org.dead.waiver` asks every `KNOWN_VIOLATIONS` entry to shrink-only; for this guard
that means the entry carries the count and a higher count fails.

### 5. Oversized files

Swift (limit 1,000 error, 400 warning): 1 over 1,000 (`SpaceSceneView.swift` 1,169, disabled inline), 86 between 400
and 1,000. The next ten: `ContentView.swift` 998, `DocumentService.swift` 960, `FicheroApp.swift` 950,
`RecipeSetupStore.swift` 895, `LibraryManager.swift` 775, `DocumentKGWebPaneCoordinatorMacOS.swift` 761,
`CanvasSceneView.swift` 752, `ContentView+DetailLayout.swift` 722, `ContentView+RootLayout.swift` 697,
`DocumentStore.swift` 694. `FicheroApp.swift` at 950 holds the scene graph, menus wiring and the two debug surfaces
(Loove coverage, SPARQL): the surfaces move out first.

Python (proposed line 1,500): 84 non-generated modules over 1,000; over 3,000: `db/__init__.py` 8,503,
`workflows/tools/vision_base.py` 6,430, `api/routes/document/segments.py` 6,150, `execution/jobs.py` 5,554,
`llm/__init__.py` 5,119, `api/routes/document/documents.py` 4,840, `api/routes/system/recipes.py` 3,658,
`workflows/tools/extractors.py` 3,590, `models/__init__.py` 3,168, `api/main.py` 3,146. Generated (exempt):
`fichero_cli/openapi_surface_generated.py` 20,272, `fichero_mcp/openapi_tools_generated.py` 10,603. Builder:
`queue.py` 1,860, `check_tool.py` 1,717.

## Proposed batches (one builder lane each)

Guards (Stage 1 of the spec; land before the moves so each move lane is judged by the rule it satisfies)
- **G0 (Step 1.0)** `check_file_placement --since <base>` beside `check_folder_organization.py`: judges every added or renamed file of
  the batch (folder by layer and feature, name convention, test mirror, nothing at the repo root or `api/routes` root, no
  `sys.modules` alias), red with the right path per file; wired in `harness.toml` `since_guards` for `fichero/` and
  `fichero-server/`; `--self-test` + a pytest over a temp repo. Owner's addition 2026-11-14: per batch, not nightly. M.
  Lands first; every move lane after it is judged by it.
- **G1 (Step 1.1)** the same guard without `--since`: the whole-tree question (root allowlist, loose modules, shim
  modules, test mirror, test names), baselined on today, `--self-test`. Python and root rules. M. Briefs for the first wave (G0, V1, G1, G2, P1, S5): `agent-work/briefs/code-org/`.
- **G2** `check_swift_one_type_per_file` (type count, View suffix, platform suffix), baselined; `check_folder_organization`
  gains the single-file-folder and layer-name rules and count-carrying allowlist entries. M.
- **G3** `check_swift_compiler_warning_ratchet` over the build rung's CLEAN build log, two buckets (hand-written, generated), +
  the builder post-step (`check_tool.py build` keeps the log path); baseline from one clean M4 build on the pinned generator;
  a generated-bucket entry needs an upstream reference. M. **Owner decision 6.**
- **V1** generator range cap in `fichero/fichero-api-client/Package.swift` (`"1.6.0"..<"1.13.0"`), `Package.resolved` kept at
  1.10.3 or moved to 1.12.2 together with the runtime it needs; a package test pins the range; lifts when upstream #947 ships.
  S. Lands before G3 so the baseline is measured on one generator.
- **G4** `check_pyright_ratchet` (nightly first) and `check_python_file_size_ratchet`. M.
- **G5** `check_vulture_ratchet` (per batch) and `check_periphery_ratchet` (nightly, needs an index build on the M4). M.

Python moves
- **P1** delete the 18 `api/routes` shims, repoint `main.py` + 31 importers; `check_openapi_route_set_current` proves the
  route set unchanged. S.
- **P2** package-root modules into their packages (list in §1), new `export/` package; one commit per module. M.
- **P3** test dirs renamed to packages (`jobs`→`execution`, `kg`→`knowledge`, `transport`→`security`, `check`→`checking`,
  `harness`→`workflows`), loose `tests/unit/*.py` into `core/` or `perf/`; prefix-numbered test renamed. M (pure `git mv`).
- **P4** one oversized module per lane: `db/__init__.py` → `db/core.py` with a re-export door; `llm/__init__.py` likewise;
  `api/routes/document/segments.py` → package; `execution/jobs.py`; `api/main.py` wiring only. L split in 5.
- **P5** `api/` transport modules → `api/transport/`; `core/egress.py`, `core/tls.py`, `core/no_model_in_get.py` to their
  domains; route-module Pydantic models → `models/<resource>.py`, one resource per lane. M each.

Swift moves (each: `git mv`, update imports of nothing (one module), run `check_xcode_registration`,
`check_folder_organization`, `check_dead_files`, build on the M4)
- **S1** `Models/` by feature, cluster 1: Segment (22), Workflow (20), Recipe (17); tests mirror. M.
- **S2** `Models/` cluster 2: Document (15), Activity (15), Library (11), Inspector (11), Sidebar (10). M.
- **S3** `Models/` cluster 3: the long tail (Reading, Entity, Setup, Mobile, Canvas, Search, Preview…) + what stays flat;
  `Models` leaves `KNOWN_VIOLATIONS`. M.
- **S4** `Services/` by feature (Workflow, Pairing, Entity, Activity, Engine, Annotation, Action, Research…), `*Types.swift`
  beside their service; `Services` leaves `KNOWN_VIOLATIONS`. M. **Owner decision 2.**
- **S5** dead code out: the 9 workflow files, `ScrollWheelZoom`, `FicheroShortcuts`, the 6 test-only types with their
  tests; `check_dead_files` allowlist shrinks by 9. S. **Owner decision 3.**
- **S6** `SpaceSceneView.swift` split (drop the `swiftlint:disable`); `FicheroApp.swift` debug surfaces out; `ContentView.swift`
  next concern out. M.
- **S7** `Views/Components/` and `Views/Library/` emptied of feature files (finding 9, 10); both leave `KNOWN_VIOLATIONS`. M.
- **S8** small folders: `Views/Models`, `Views/Prototypes`, `Views/SPARQLConsole`, `Views/Auth`, `Views/LooveCoverage`,
  `App/` views, `Views/Shell` and `Views/Preview` loose files; `Shell/Toolbar/WorkflowBar/`, `ContentView/State|Search/`. M.
- **S9** names: platform suffix outliers, `Views/Workflow/Library` → `Picker`, `FocusedCommandButtons+*.swift` into
  one-type files under `App/Menus/FocusedCommands/<Verb>/`. M. **Owner decision 4.**

Order: G0, V1, G1, G2 first (they judge everything after); P1, S5 next (pure deletion, lowest risk, highest tidiness per line);
then P2–P3 and S1–S4 interleaved so the Python and Swift lanes share no file; G3–G5 any time the M4 is free; P4, P5, S6–S9
after.

## Owner rulings (2026-11-14)

All six questions ruled, folded into the spec's bullets: view-local state beside its view, `Models/` for shared state;
`*Types.swift` bundles kept; the six test-only types deleted with their tests (S5); `IOS`/`MacOS`; Python size line 1,500 as
a ratchet; the compiler-warnings baseline in `scripts/`.
