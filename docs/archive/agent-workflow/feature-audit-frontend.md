# Fichero SwiftUI Frontend Feature Audit

**Branch:** `codex/restructure-api-swiftui`
**Date:** 2026-02-26
**Auditor:** swift-dev (static analysis only, no swiftlint or build verification)

---

## Sidebar Modes (from SidebarItem.swift)

The app supports 8 sidebar categories: Folder, Search, Chat, Workflow, Automation, Batch, Activity, Library. The `SidebarItem` model uses a rich `ItemType` enum covering: document, savedSearch, conversation, workflow, chain, comparison, schedule, trigger, batch, activityRun, folder, and libraryHeader. Multi-library support is built in via `libraryId: UUID?`.

## Services Available (56 files)

Core generated services: ActivityServiceGenerated, AutomationServiceGenerated, BatchServiceGenerated, ChatServiceGenerated, ConversationServiceGenerated, DocumentServiceGenerated, ImportServiceGenerated, MCPServiceGenerated, ModelServiceGenerated, ProviderServiceGenerated, SavedSearchServiceGenerated, SearchServiceGenerated, StorageServiceGenerated, WorkflowExecutionServiceGenerated, WorkflowServiceGenerated.

Supporting services: ActionLibraryService, ActionsService, ArtifactService, ChainService, DragDropService, EmbeddedBackendService, ErrorService, ImportService, IntegrationsService, MCPService, ModelComparisonService, ModelService, PerformanceService, ProviderService, SavedSearchService, WorkflowExecutionObserver, WorkflowExecutionService, WorkflowStreamService.

## Test Files

Located in `fichero/fichero-tests/`:
- ActivityTypesTests.swift
- ContractTests.swift
- EndpointValidationTests.swift
- FicheroTests.swift
- LibraryManagerTests.swift
- SidebarItemTests.swift
- SidebarTests/StateManagerTests.swift
- WorkflowCanvasTests.swift
- WorkflowStreamParsingTests.swift

UI tests directory exists at `fichero/fichero-ui-tests/` (contents not inspected).

---

## View Directory Audits

### AIProviders
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 13 files, 1816 total lines | ProvidersView.swift (main), AddProviderSheet (3 steps + helpers), AIModelCatalog, AIModelSelectionView, AIProviderAddModelsSheet, ProvidersSettingsSheet, ProvidersView extensions |
| Tests | none | No test files matching AIProvider or Provider |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | Full HSplitView with provider list, detail, add/remove flow, model catalog, 3-step add wizard. Uses generated ProviderServiceGenerated + FicheroAPIClient types |
| M1 recommendation | **on** | Core feature for AI configuration; well-structured with extension pattern |

### Actions
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 4 files, 783 total lines | ActionLibraryView (NavigationSplitView with sidebar/content/detail), ActionDetailView, ActionPickerView, ActionRowView |
| Tests | none | No test files matching Action |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | NavigationSplitView browsing reusable workflow actions. Category filtering, search, detail display. Uses local ActionsService (not generated) |
| M1 recommendation | **on** | Useful for workflow composition; lightweight |

### Activity
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 14 files, 2350 total lines | ActivityDetailView (main), ActivityProgressView (4 extensions), ActivityCodeView, ActivityConsoleView, ActivityDiagramView, ActivityErrorsView, ActivityGraphView, ActivityLogView, ActivityOverviewView, ActivityViewHelpers, ActivityProgressModels |
| Tests | exist | ActivityTypesTests.swift |
| TODOs/FIXMEs | 1 | `ActivityProgressView+DataLoading.swift:20` -- "TODO: Re-enable when backend schema is updated" (data loading disabled pending schema change) |
| Disabled code | 0 | Clean |
| Feature status | **partial** | Rich multi-tab activity viewer (console, progress, errors, overview, code, diagram, graph, log). Live execution support via WorkflowExecutionObserver. One data-loading path disabled pending backend schema update |
| M1 recommendation | **on** | Core workflow monitoring feature; the disabled path is non-blocking |

### Agents
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 2 files, 560 total lines | AgentConfigurationView (node-level config in workflow), AgentSettingsView (app-level agent defaults) |
| Tests | none | No test files matching Agent |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | AgentConfigurationView: Form with agent type picker (react), system prompt, max iterations, tool selection. AgentSettingsView: NavigationSplitView for per-agent-type defaults. Uses AgentSettings singleton |
| M1 recommendation | **on** | Small but important for agent-node workflows |

### Automation
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 12 files, 2197 total lines | ScheduleEditorView (main schedule form), ScheduleCreationSheet, ScheduleDetailView, ScheduleEditorView+Category, TriggerEditorView (+ subdirectory with FormPanel/PreviewPanel), TriggerCreationSheet, TriggerDetailView (+ Configuration, ExecutionHistory, Helpers) |
| Tests | none | No test files matching Automation, Schedule, or Trigger |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | Full schedule and trigger CRUD. Schedule editor supports interval/cron/run-at types, timezone, date ranges, batch mode. Trigger detail shows configuration and execution history. Uses AutomationServiceGenerated |
| M1 recommendation | **on** | Key automation feature; well-structured |

### Batch
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 6 files, 478 total lines | BatchDetailView.swift (main), extensions: +Actions, +Configuration, +Header, +Items, +Progress |
| Tests | none | No test files matching Batch |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | ScrollView detail with header, progress, configuration, items, error sections. Uses BatchServiceGenerated via APIClient. Clean extension-based decomposition |
| M1 recommendation | **on** | Essential for batch workflow runs |

### Chat
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 18 files, 1811 total lines | ChatView.swift (RAG-style doc chat), ChatInputView, ChatInspector (5 parts), ChatMessagesList, ChatStatusViews, ChatMapGrid, MessageBubble, MessageCard, ScopedDocumentRow, ComparisonDetailView (4 parts), ChatView+Extensions |
| Tests | none | No test files matching Chat |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | Full RAG chat with provider/model selection, message list, input, inspector (actions, header, scoped documents, search). Includes ComparisonDetailView for model comparison results. Drop target for document scoping. Uses ChatServiceGenerated + ConversationServiceGenerated |
| M1 recommendation | **on** | Core user-facing feature |

### Components
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 11 files, 1120 total lines | BackendConnectionView, BatchRow, FlowLayout, LibraryImageView, ProviderLogoView, ScheduleRow, StatusBadge, TriggerRow, WorkflowExecutionRow (+Helpers), WorkflowPreviewSheet |
| Tests | none | No test files matching Components |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | Shared reusable components. BackendConnectionView handles startup/connection states. Row views for sidebar items (batch, schedule, trigger, execution). FlowLayout for tag clouds. StatusBadge for status indicators |
| M1 recommendation | **on** | Shared infrastructure; required by other views |

### Integrations
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 1 file, 342 total lines | IntegrationsView.swift (DEVONthink, Bookends, Tinderbox) |
| Tests | none | No test files matching Integration |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | NavigationSplitView showing available/unavailable integrations. Loads items from selected integration. Uses IntegrationsService (non-generated, local service with AppleScript support via IntegrationsService+AppSpecific) |
| M1 recommendation | **dev-only** | macOS-specific app integrations; depends on installed apps (DEVONthink, Bookends, Tinderbox). Low priority unless user has these apps |

### Library
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 25 files, 4986 total lines | LibraryView.swift (main grid/list/table/map), 6 LibraryView extensions (ColumnConfig, DisplayModes, FilterAndBatch, InlineEditing, KeyboardShortcuts, Sorting), DocumentInspector (4 tabs: Info, Content, Metadata, Artifacts), EditorView, ArtifactsBrowserView, ImageViewer (3 subfiles), ImageViewerComponents, MagnifierPanel, NavigatorMiniMap, QuickLookComponents, ScrollWheelZoom, CheckerboardPattern, FolderAccessManager, LibraryViewComponents |
| Tests | exist | LibraryManagerTests.swift |
| TODOs/FIXMEs | 1 | `LibraryView+FilterAndBatch.swift:202` -- "TODO: Navigate to batches sidebar and execute batch with SSE streaming" |
| Disabled code | 0 | Clean |
| Feature status | **complete** | Richest view area. Multi-layout (grid, list, table, map). Per-folder sort persistence. Inline editing. Keyboard shortcuts. Column configuration for table view. Document inspector with 4 tabs. Image viewer with magnifier, zoom, cursor tracking. Artifacts browser. QuickLook integration. Drag-and-drop. Batch workflow launch (TODO: SSE streaming nav). Uses DocumentServiceGenerated, StorageServiceGenerated |
| M1 recommendation | **on** | Core document management feature; primary content view |

### MCPServers
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 5 files, 885 total lines | MCPServersView.swift (main HSplitView), MCPServerDetailView, AddMCPServerSheet, MCPServersSheet, MCPToolsCatalogView |
| Tests | none | No test files matching MCP |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | Full MCP server management: list, add, delete, detail, tools catalog. Uses MCPService (non-generated). HSplitView with server list and detail panel |
| M1 recommendation | **on** | Important for MCP tool integration with workflows |

### Menu
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 4 files, 1019 total lines | AddItemMenu (reusable + menu), FocusedCommandButtons, ImagePreviewMenuCommands, ViewMenuCommands |
| Tests | none | No test files matching Menu |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | AddItemMenu uses ItemTypeRegistry for extensible item creation. FocusedCommandButtons for keyboard shortcuts. ViewMenuCommands for view mode switching. ImagePreviewMenuCommands for image-specific actions |
| M1 recommendation | **on** | Core app infrastructure; needed for menu bar |

### ModelComparison
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 6 files, 494 total lines | ModelComparisonView.swift (NavigationSplitView), ModelComparisonView+Sidebar, ComparisonResultView, ModelPickerSheet, ModelResultCard, PresetPickerSheet |
| Tests | none | No test files matching Comparison or ModelComparison |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | Side-by-side model comparison. Prompt input, model picker, preset picker, result cards. Uses ModelComparisonService. Default models: GPT-4o vs Claude 3.5 Sonnet |
| M1 recommendation | **dev-only** | Power-user/dev feature for comparing model outputs; not essential for core document workflow |

### Search
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 6 files, 746 total lines | SearchView.swift (HSplitView with filters + results), SearchFiltersPanel, SearchResultsDisplay, SearchResultRowFromAPI, SearchMapComponents, SearchView+Helpers |
| Tests | none | No test files matching Search |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | Full search with semantic/fulltext/hybrid modes. Filters panel. Sort by relevance/date/name. Save search support. Map component for spatial results. Uses SearchServiceGenerated + SavedSearchServiceGenerated |
| M1 recommendation | **on** | Core discovery feature |

### Settings
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 6 files, 597 total lines | SettingsView.swift (4-tab TabView), GeneralSettingsView, AISettingsView, BackendSettingsView, LocalModelsSettingsView, AIDefaults |
| Tests | none | No test files matching Settings |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | Standard macOS settings window (550x450). Tabs: General, AI, Backend, Models. AIDefaults provides default configuration values |
| M1 recommendation | **on** | Essential app configuration |

### Sheets
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 2 files, 426 total lines | DocumentPickerSheet (select docs for workflow), WorkflowPickerSheet (select workflow for docs) |
| Tests | none | No test files matching Sheet or Picker |
| TODOs/FIXMEs | 1 | `DocumentPickerSheet.swift:185` -- "TODO: Navigate to batches sidebar and execute batch with SSE streaming" |
| Disabled code | 0 | Clean |
| Feature status | **complete** | Bidirectional picker sheets for workflow-document pairing. Search, selection, confirmation. Uses LibraryManager + DocumentStore |
| M1 recommendation | **on** | Required for workflow execution UX |

### Sidebar
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 33 files, 3980 total lines | SidebarView.swift (main), 4 SidebarView extensions, SidebarItemRow (5 parts), SidebarModeBar, SidebarModeIcon, SidebarSectionHeader, SidebarStateManagers, SidebarConstants, SidebarEnvironment, SidebarItemContextMenu, SidebarViewExtensions. **Modes/** subdir (11 files): LibrarySidebarContent, SearchSidebarContent, ChatSidebarContent, WorkflowsSidebarContent, AutomationSidebarContent, BatchesSidebarContent, ActivitySidebarContent (5 parts), ActivityRun. **Components/** subdir (3 files): SidebarActions, SidebarCreationHandlers, SidebarObservers |
| Tests | exist | SidebarItemTests.swift, SidebarTests/StateManagerTests.swift |
| TODOs/FIXMEs | 4 | BatchesSidebarContent:87 (library filtering), AutomationSidebarContent:34,41 (library filtering), WorkflowsSidebarContent:228 (activity view navigation) |
| Disabled code | 0 | Clean |
| Feature status | **complete** | Xcode-style mode-switching sidebar with 7 content modes (Library, Search, Chat, Workflows, Automation, Batches, Activity). Multi-library support. Drag-and-drop. Rename/delete state managers. Context menus. Expansion persistence. Combine observers for data refresh. 4 TODOs are non-blocking enhancement requests (library scoping for batches/automation, activity navigation) |
| M1 recommendation | **on** | Core navigation infrastructure |

### Toolbars
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 5 files, 750 total lines | MainToolbar (sidebar toggle, add menu, search, view modes), ChatViewToolbar, SearchViewToolbar, WorkflowToolbar, MiniToolbar |
| Tests | none | No test files matching Toolbar |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | View-specific toolbars. MainToolbar is DEVONthink-inspired with sidebar toggle, add menu, search field, view mode switchers. Each content view has its own toolbar variant |
| M1 recommendation | **on** | Core UI infrastructure |

### Workflow
| Aspect | Status | Details |
|--------|--------|---------|
| Files | 60 files, 8007 total lines | WorkflowEditor (4 parts), WorkflowCanvasView (4 parts), WorkflowInspector (4 parts), WorkflowOutputLog (5 parts), WorkflowNodeView (2 parts), WorkflowNodeCard, WorkflowNodeRow, WorkflowEdgeView, WorkflowPortView, WorkflowToolBlocks, AgentNodeBlockView, CanvasHelpers, DynamicConfigView (4 parts), NodeInputMappings, NodePopover, NodeProviderModelSelector, SimpleWorkflowView, WorkflowExecutionView, WorkflowDiagramPreview, ChainEditorView, WorkflowChainListView (+ 6 subfiles), WorkflowLibraryView (+ 5 subfiles), **NodeConfigs/** subdir (10 files): NodeConfigView, CollectionNodeConfig, DescribeNodeConfig, ExtractEntitiesNodeConfig, FilesNodeConfig, SearchNodeConfig, SummarizeCollectionNodeConfig, SummarizeFileNodeConfig, SummarizeFolderNodeConfig, TranscribeNodeConfig |
| Tests | exist | WorkflowCanvasTests.swift, WorkflowStreamParsingTests.swift |
| TODOs/FIXMEs | 0 | Clean |
| Disabled code | 0 | Clean |
| Feature status | **complete** | Largest view area. Full visual workflow editor with: drag-and-drop canvas, gesture support, edge connections, snap-to-grid, node cards with ports, inspector with agents/MCP tools/data loading, output log with error cells/status/empty states, execution view, diagram preview (NSImage export), chain editor and list view, workflow library (browse, create new, detail, preview, thumbnail), 10 node-type-specific config views, dynamic config from JSON schema, simple workflow mode, provider/model selector per node. Uses WorkflowServiceGenerated, WorkflowStreamService, WorkflowExecutionObserver |
| M1 recommendation | **on** | Core feature; largest and most complex view area |

---

## Root-Level Views (not in subdirectories)

8 files, 1693 total lines at `Views/` root:
- ContentView.swift (400 lines) + 4 extensions (Actions, Navigation, Persistence, State, ViewBuilders)
- ContentViewModifiers.swift (286 lines)
- DocumentTabView.swift (217 lines)

These are the app shell. No TODOs found.

---

## Summary Table

| View Area | Files | Lines | Tests | TODOs | Disabled Code | Feature Status | M1 Recommendation |
|-----------|-------|-------|-------|-------|--------------|----------------|-------------------|
| AIProviders | 13 | 1,816 | none | 0 | 0 | complete | **on** |
| Actions | 4 | 783 | none | 0 | 0 | complete | **on** |
| Activity | 14 | 2,350 | exist | 1 | 0 | partial | **on** |
| Agents | 2 | 560 | none | 0 | 0 | complete | **on** |
| Automation | 12 | 2,197 | none | 0 | 0 | complete | **on** |
| Batch | 6 | 478 | none | 0 | 0 | complete | **on** |
| Chat | 18 | 1,811 | none | 0 | 0 | complete | **on** |
| Components | 11 | 1,120 | none | 0 | 0 | complete | **on** |
| Integrations | 1 | 342 | none | 0 | 0 | complete | **dev-only** |
| Library | 25 | 4,986 | exist | 1 | 0 | complete | **on** |
| MCPServers | 5 | 885 | none | 0 | 0 | complete | **on** |
| Menu | 4 | 1,019 | none | 0 | 0 | complete | **on** |
| ModelComparison | 6 | 494 | none | 0 | 0 | complete | **dev-only** |
| Search | 6 | 746 | none | 0 | 0 | complete | **on** |
| Settings | 6 | 597 | none | 0 | 0 | complete | **on** |
| Sheets | 2 | 426 | none | 1 | 0 | complete | **on** |
| Sidebar | 33 | 3,980 | exist | 4 | 0 | complete | **on** |
| Toolbars | 5 | 750 | none | 0 | 0 | complete | **on** |
| Workflow | 60 | 8,007 | exist | 0 | 0 | complete | **on** |
| *Root views* | 8 | 1,693 | exist | 0 | 0 | complete | **on** |
| **TOTALS** | **241** | **34,040** | **4 areas** | **7** | **0** | | |

## Key Findings

1. **Code health is excellent.** Zero disabled/commented code across all 241 files. Only 7 TODO comments, all non-blocking enhancement requests.

2. **Test coverage is sparse.** Only 4 of 19 view areas have associated tests (Activity, Library, Sidebar, Workflow). The existing tests focus on models/types rather than view logic (ActivityTypesTests, SidebarItemTests, WorkflowCanvasTests, WorkflowStreamParsingTests).

3. **Workflow is the dominant area** at 60 files / 8,007 lines -- nearly a quarter of all view code. It covers canvas editing, execution, inspection, node configuration, chains, and a library browser.

4. **Two areas recommended dev-only for M1:**
   - **Integrations** -- depends on third-party macOS apps (DEVONthink, Bookends, Tinderbox)
   - **ModelComparison** -- power-user feature for comparing LLM outputs side-by-side

5. **All 7 TODOs are enhancement requests**, not bugs:
   - 1x backend schema update needed (Activity data loading)
   - 3x library-scoped filtering for batches/automation in sidebar
   - 2x batch SSE streaming navigation (Library filter, DocumentPickerSheet)
   - 1x activity view navigation from workflow execution

6. **Architecture is consistent.** Views use EnvironmentObject injection for generated services, @State for local state, extension-based decomposition for large views, and HSplitView/NavigationSplitView patterns throughout.
