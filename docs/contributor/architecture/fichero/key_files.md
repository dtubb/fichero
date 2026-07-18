(AI generated. Not reviewed.)

# Frontend Key Files

**Last Updated**: 2026-05-24

A navigation map of the SwiftUI app (`fichero/fichero/`). Line counts are approximate and only noted where a file is large enough to be worth splitting attention. Use jCodemunch (`search_symbols`, `get_file_outline`) to locate exact symbols rather than grepping.

## Entry Points

- **`FicheroApp.swift`** (repo root of the app target) — `@main` App, command menus, window/scene setup.
- **`App/`** — app-lifecycle and window scaffolding:
  - `AppState.swift` — global `@Observable`/`ObservableObject` app state.
  - `ViewSettings.swift` — layout/view preferences.
  - `LibraryWindow.swift` — per-library window scene.
  - `WelcomeView.swift` — first-run / welcome surface.
  - `AppInstaller.swift`, `SparkleUpdater.swift` — install + Sparkle auto-update.
- **`Views/ContentView.swift`** + extensions — the main resizable multi-pane layout, split across:
  `ContentView+State.swift`, `+ViewBuilders.swift`, `+Navigation.swift`, `+Actions.swift`, `+Persistence.swift`, and `ContentViewModifiers.swift`.
- **`Views/DocumentTabView.swift`** — per-window entry point, service initialization.

## Layout

The window is a **resizable multi-pane reading layout** (not a fixed three-column split):
sidebar · document list · content/PDF reading view · tabbed inspector. Pane widths persist
via `@SceneStorage`. The reading layout and page navigation live in
`ContentView+ViewBuilders.swift` and `Views/Library/PDFThumbnailView.swift`.

## Views (`Views/`, ~234 files across ~19 feature domains)

### Library (`Views/Library/`) — document browser, preview, inspector
- `DocumentInspector.swift` (~1,150 lines) + `DocumentInspector/` folder — **inspector V2**, tabbed:
  - `DocumentInspectorInfoTab.swift`, `DocumentInspectorMetadataTab.swift`,
    `DocumentInspectorContentTab.swift`, `DocumentInspectorArtifactsTab.swift`
  - `AttributedTextEditor.swift` — rich-text editor (`NSViewRepresentable`)
- `PDFThumbnailView.swift` (~850 lines) — PDF rendering, page thumbnails, reading-view plumbing (PDFKit bridge)
- `LibraryView.swift` + extensions (`+DisplayModes`, `+ColumnConfig`, `+Sorting`, `+FilterAndBatch`, `+InlineEditing`, `+KeyboardShortcuts`) and `LibraryViewComponents.swift` — grid/list/table browser
- `EditorView.swift` (~360 lines) — document editor surface
- `ImageViewer/`, `ImageViewerComponents.swift`, `MagnifierPanel.swift`, `ScrollWheelZoom.swift` — image preview + magnifier (AppKit bridges)
- `QuickLookComponents.swift`, `FolderAccessManager.swift` — Quick Look + security-scoped bookmark access
- `FolderContentsGrid.swift`, `NavigatorMiniMap.swift`

### Sidebar (`Views/Sidebar/`) — multi-mode navigation
- `SidebarView+ViewComponents.swift` (~760 lines), `SidebarItemRow.swift` (~680), `SidebarItemRow+DropHandlers.swift`, `SidebarViewExtensions.swift`
- Modes: Library, Search, Chat, Workflows, Activity, Automation, Batches

### Workflow (`Views/Workflow/`) — visual LangGraph editor
- `WorkflowLibraryView.swift` (~550), `WorkflowCanvasView.swift` (~430), `WorkflowEdgeView.swift`, `WorkflowNodeView.swift`, port/output views

### KnowledgeGraph (`Views/KnowledgeGraph/`)
- `EntityDigestView.swift` — KG entity/claim digests; backing for inspector KG tab and graph views

### Other domains
`Chat/`, `Library/Search/`, `Activity/`, `Settings/AIProviders/`, `Library/Automation/`, `Agents/`, `Integrations/`,
`Settings/MCPServers/`, `Chat/ModelComparison/`, `Settings/`, `Sheets/`, `Shell/Menu/`, `Toolbars/`, `Components/`, `Library/Actions/`.

## Services (`Services/`, ~49 files)

### Generated (14 `*Generated.swift` — wrap the OpenAPI client, typed methods)
`Activity`, `Artifact`, `Automation`, `Batch`, `Chat`, `Conversation`, `Document`, `Import`,
`Model`, `Provider`, `SavedSearch`, `Search`, `Storage`, `Workflow` — all `…ServiceGenerated.swift`.
**Do not hand-edit** the generated OpenAPI client under `fichero-api-client/Sources/…`; the
`*Generated.swift` wrappers, despite the suffix, ARE hand-written and editable.

### Hand-written services / wrappers
- `APIClient.swift` (~450) — HTTP client, `X-Fichero-Library-Path` injection, `addEngineAuth` shared-secret
- `EmbeddedBackendService.swift` — engine process lifecycle
- `WorkflowStreamService.swift`, `WorkflowExecutionService.swift` — SSE workflow execution
- `MCPService.swift`, `ActionsService.swift`, `ActionLibraryService.swift`, `IntegrationsService.swift`,
  `ModelComparisonService.swift`, `PerformanceService.swift`, `AppleScriptCommands.swift`
- `ProviderService` wraps `ProviderServiceGenerated` (validation/business logic pattern)

## Models (`Models/`, ~42 files)

- `Document.swift` (~390) — core model: `DocType`, `FileType`, `Status`
- `DocumentStore.swift` + `DocumentStore+CRUD.swift` + `+Helpers.swift` — document hierarchy, CRUD, import
- `LibraryManager.swift` + `LibraryManager+Operations.swift` — multi-library orchestration
- `WorkflowStore.swift` (~510), `WorkflowTypes.swift`, `WorkflowToolTypes.swift`, `WorkflowChain.swift`
- `SidebarItem.swift`, `SidebarItemBuilder.swift`, `ItemTypeRegistry.swift` — sidebar data model (ids are type-prefixed, e.g. `doc:UUID`)
- `FicheroDocument.swift` — per-window document state
- `FeatureManager.swift` — feature flags / tier gating in the UI
- `MCPServer.swift`, `Trace.swift`, `Run.swift`

## Generated API client (`fichero-api-client/`)
Local Swift package generated by Apple's Swift OpenAPI Generator from
`fichero-engine/tests/contracts/openapi.json`. Regenerate via
`fichero-engine/scripts/sync_openapi_schema.sh`. See `api_client.md`.

## Notes for navigation
- New `.swift` files in the `Fichero` main target must be registered with
  `ruby scripts/add-swift-file.rb <path>` — a file on disk is invisible to the compiler until then.
- Prefer jCodemunch tools (`search_symbols`, `get_file_outline`, `find_references`) over `find`/`grep`.
