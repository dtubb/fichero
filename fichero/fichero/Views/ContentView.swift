import OSLog
import SwiftUI
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ContentView")
// swiftlint:disable file_length

/// Identifies which main pane has keyboard focus for Tab cycling
enum PaneFocus: Hashable {
    case sidebar, content, preview, inspector
}

// Main content view with three-column navigation
// Switches between Library, Search, and Workflow views based on sidebar selection
//
// Architecture: This view has been refactored into multiple extensions for maintainability:
// - ContentView+State: Computed properties and state helpers
// - ContentView+ViewBuilders: View builders for sidebar, content, preview, inspector
// - ContentView+Navigation: Content routing based on AppViewMode
// - ContentView+Actions: Action handlers and business logic
// - ContentView+Persistence: State serialization for @SceneStorage
// swiftlint:disable:next type_body_length
struct ContentView: View {
    static let inspectorMinWidth: Double = 250
    static let inspectorMaxWidth: Double = 1000
    static let contentMinWidth: Double = 520
    static let contentMaxWidth: Double = 2200
    /// Minimum width of the widescreen content-list pane. Clamped to the
    /// view-mode icon rail width so the rail and list rows (thumbnail + text)
    /// can't be dragged narrow enough to clip (#1243). Derived from the rail:
    /// 4 mode icons × 40pt + MiniToolbar horizontal padding (12×2) + inter-item
    /// spacing (12) ≈ 240.
    static let contentListMinWidth: Double = 240

    // MARK: - Environment

    @EnvironmentObject var viewSettings: ViewSettings
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var apiClient: APIClient
    @EnvironmentObject var documentStore: DocumentStore
    @EnvironmentObject var conversationService: ConversationServiceGenerated
    @EnvironmentObject var importService: ImportServiceGenerated
    @EnvironmentObject var windowState: WindowState
    @EnvironmentObject var workflowStore: WorkflowStore
    @EnvironmentObject var savedSearchService: SavedSearchServiceGenerated
    @EnvironmentObject var workflowStreamService: WorkflowStreamService
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    @Environment(KGFocusState.self) var kgFocusState
    @EnvironmentObject var claimFocusState: ClaimFocusState
    @EnvironmentObject var researchService: ResearchService

    // MARK: - State (synced with @SceneStorage for persistence)

    // Runtime state - full objects for use in views
    @State var viewMode: AppViewMode = .library(nil)
    @State var detailDocument: Document?
    @State var columnVisibility: NavigationSplitViewVisibility = .all
    @State var browserSelection: Set<String> = []

    // Persisted state (@SceneStorage) - synced via .onAppear and .onChange
    @SceneStorage("selectedSidebarItem") var selectedSidebarItemId: String?
    @SceneStorage("columnVisibilityRaw") var columnVisibilityRaw: Int = 2 // 2 = .all
    @SceneStorage("browserSelectionData") var browserSelectionData: Data = Data()
    @SceneStorage("viewModeType") var storedViewModeType: String = "library"
    @SceneStorage("viewModeItemId") var storedViewModeItemId: String?

    // Workflow state
    @State var editingWorkflow: Workflow = Workflow(name: "New Workflow", description: "")

    // Chat state (shared between ChatView and ChatInspectorView)
    @State var chatSelectedDocuments: Set<String> = []

    // Main toolbar state (per-window persistence)
    @SceneStorage("viewDisplayMode") var viewDisplayMode: ViewDisplayMode = .icon

    /// Global default — survives window close, fresh launches, even
    /// when no per-folder override exists. Solves the "set List, switch
    /// items, reverts to Icon" complaint in #943. Synced with
    /// viewDisplayMode every time the user changes view mode via
    /// updateViewDisplayMode; consulted as the fallback when neither
    /// SceneStorage nor a per-folder save has a value.
    @AppStorage("library.defaultViewDisplayMode")
    var defaultLibraryViewDisplayMode: ViewDisplayMode = .icon
    @SceneStorage("currentLayoutMode") var currentLayoutMode: LayoutMode = .widescreen
    @SceneStorage("sidebarMode") var sidebarMode: SidebarMode = .library

    // Column visibility persistence
    @AppStorage("sidebarWidth") var sidebarWidth: Double = 280
    @AppStorage("contentWidth") var contentWidth: Double = 600
    @AppStorage("inspectorWidth") var inspectorWidth: Double = 300
    @AppStorage("widescreenContentPaneWidth") var widescreenContentPaneWidth: Double = 320
    @AppStorage("pageListWidth") var pageListWidth: Double = 120
    @AppStorage("pageContentPaneWidth") var pageContentPaneWidth: Double = 200
    @SceneStorage("showSidebar") var showSidebar: Bool = true
    @SceneStorage("showInspectorSidebar") var showInspectorSidebar: Bool = true
    @SceneStorage("showDocumentGrid") var showDocumentGrid: Bool = true

    // Map view persistence (latitude, longitude, zoom)
    @SceneStorage("mapLatitude") var mapLatitude: Double = 0.0
    @SceneStorage("mapLongitude") var mapLongitude: Double = 0.0
    @SceneStorage("mapZoom") var mapZoom: Double = 1.0
    @SceneStorage("sidebarWindowPersistenceId") var sidebarWindowPersistenceId: String = UUID().uuidString

    // Per-folder view mode persistence (JSON-encoded [folderId: displayMode.rawValue], per-window)
    @SceneStorage("folderViewDisplayModes") var folderViewDisplayModesJSON: String = "{}"

    @StateObject var itemRegistry = ItemTypeRegistry()
    @StateObject var performanceService = PerformanceService()
    @StateObject var documentScrollSync = DocumentScrollSyncState()
    @State var toolbarSearchText: String = ""
    @State var navigationHistory = AppNavigationHistory()
    @State var isRestoringNavigationHistory = false

    // Error service (using singleton pattern)
    @ObservedObject var errorService = ErrorService.shared
    @ObservedObject var featureManager = FeatureManager.shared
    @ObservedObject var workflowRunProviderCache = WorkflowRunProviderCache.shared

    // Pane focus state for Tab cycling
    @FocusState var focusedPane: PaneFocus?

    // Drag and drop state
    @State var isDropTargeted = false
    @State var isImporting = false
    @State var importProgress: String?
    @State var importError: String?

    // MARK: - Body

    var body: some View {
        Group {
            if appState.isCheckingBackend {
                // Show loading while checking API
                VStack(spacing: 16) {
                    ProgressView()
                        .scaleEffect(1.5)
                    Text("Connecting to backend...")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if !appState.isBackendRunning {
                // API not running - show error
                VStack(spacing: 20) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 64))
                        .foregroundColor(.orange)

                    Text("Backend Not Running")
                        .font(.title)
                        .fontWeight(.bold)

                    Text(appState.backendError ?? "Cannot connect to the Fichero API server.")
                        .multilineTextAlignment(.center)
                        .foregroundColor(.secondary)
                        .frame(maxWidth: 400)

                    HStack(spacing: 16) {
                        Button("Retry") {
                            Task { @MainActor in
                                await appState.checkBackendHealth()
                            }
                        }
                        .keyboardShortcut("r", modifiers: [.command])

                        Button("Quit") {
                            NSApplication.shared.terminate(nil)
                        }
                        .keyboardShortcut("q", modifiers: [.command])
                    }
                    .padding(.top, 10)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                mainContentView
                    .onAppear {
                        logger.info("⏱ ContentView first-frame — main content visible")
                    }
            }
        }
        .onKeyPress(.tab, phases: .down) { keyPress in
            cyclePaneFocus(reverse: keyPress.modifiers.contains(.shift))
            return .handled
        }
        .onKeyPress(characters: CharacterSet(charactersIn: "\u{19}"), phases: .down) { _ in
            // Shift+Tab can arrive as back-tab (U+0019) rather than Tab+Shift.
            cyclePaneFocus(reverse: true)
            return .handled
        }
        // Option+Left/Right cycles between panes (sidebar → content → preview → inspector).
        // Plain left/right are reserved for inner-pane navigation (grid columns, DisclosureGroup expand).
        // Command+Left/Right navigates to previous/next sibling document (#593).
        .onKeyPress(.leftArrow, phases: .down) { keyPress in
            if keyPress.modifiers.contains(.command) {
                navigateSiblingPrevious()
                return .handled
            }
            if keyPress.modifiers.contains(.option) {
                cyclePaneFocus(reverse: true)
                return .handled
            }
            return .ignored
        }
        .onKeyPress(.rightArrow, phases: .down) { keyPress in
            if keyPress.modifiers.contains(.command) {
                navigateSiblingNext()
                return .handled
            }
            if keyPress.modifiers.contains(.option) {
                cyclePaneFocus(reverse: false)
                return .handled
            }
            return .ignored
        }
        .sheet(isPresented: Binding(
            get: { appState.isBackendRunning && !featureManager.firstRunCompleted },
            set: { if !$0 { featureManager.firstRunCompleted = true } }
        )) {
            FirstRunWindow()
                .environmentObject(appState)
                .environmentObject(apiClient)
        }
        .alert(item: $errorService.currentAlert) { errorModel in
            let message = errorModel.recoverySuggestion != nil ?
                "\(errorModel.message)\n\n\(errorModel.recoverySuggestion!)" :
                errorModel.message

            return Alert(
                title: Text(errorModel.title),
                message: Text(message),
                primaryButton: .default(Text("OK")) {
                    errorService.currentAlert = nil
                },
                secondaryButton: errorModel.isRecoverable ?
                    .default(Text("Retry")) {
                        // User requested retry - could trigger recovery action
                        errorService.currentAlert = nil
                    } : .cancel(Text("Dismiss")) {
                        errorService.currentAlert = nil
                    }
            )
        }
    }

    /// Main app content (when backend is connected)
    @ViewBuilder
    private var mainContentView: some View {
        // Inspector is a window-level sibling of NavigationSplitView so it
        // persists across all view modes (#1199). The HStack wrapper keeps the
        // inspector column stable while NavigationSplitView handles sidebar +
        // content navigation entirely within its detail column.
        //
        // The split-view column itself carries a very long chained-modifier
        // list (toolbar + ~16 .onChange/.onReceive handlers). To keep any single
        // `some View` expression inside the Swift type-checker's complexity
        // budget, that chain is broken across two intermediate properties:
        // `navigationSplitColumn` (NavigationSplitView + first half of modifiers)
        // and `decoratedNavigationSplitColumn` (the remaining modifiers).
        HStack(spacing: 0) {
            decoratedNavigationSplitColumn

            if showInspectorSidebar {
                ResizableDivider(
                    width: $inspectorWidth,
                    minWidth: ContentView.inspectorMinWidth,
                    maxWidth: ContentView.inspectorMaxWidth
                )
                detailView
                    .frame(width: CGFloat(inspectorWidth))
            }
        } // end HStack — inspector is window-level, not inside NavigationSplitView (#1199)

        // Listen for claim selection from inspector and sync to other panes
        .onReceive(NotificationCenter.default.publisher(for: .claimSelectedInInspector)) { notification in
            if let claimId = notification.userInfo?["claimId"] as? String {
                ClaimFocusState.shared.selectClaim(claimId: claimId)
            }
        }
    }

    /// NavigationSplitView + the FIRST half of its modifier chain.
    /// Split out of `mainContentView` so no single `some View` expression
    /// exceeds the Swift type-checker's complexity budget (#"unable to
    /// type-check this expression in reasonable time").
    @ViewBuilder
    private var navigationSplitColumn: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            sidebarContent
        } detail: {
            centerContent
                .frame(minWidth: CGFloat(ContentView.contentMinWidth), maxWidth: .infinity)
        }
        // Avoid duplicate generic per-column title pills in macOS split view.
        .navigationTitle(toolbarTitle)
        .toolbar(removing: .sidebarToggle)
        .onAppear { handleOnAppear() }
        .onChange(of: documentStore.collections) { old, new in
            handleCollectionsChange(old: old, new: new)
        }
        .onChange(of: documentStore.currentDocuments) { _, newDocs in
            handleCurrentDocumentsChange(newDocs)
        }
        .onChange(of: showInspectorSidebar) { _, newValue in
            if viewSettings.showInspector != newValue {
                viewSettings.showInspector = newValue
            }
            updateColumnVisibility()
        }
        .onChange(of: viewSettings.showInspector) { _, newValue in
            if showInspectorSidebar != newValue {
                withAnimation(.easeInOut(duration: 0.2)) {
                    showInspectorSidebar = newValue
                }
            }
        }
        .toolbar { mainToolbarContent }
        .onChange(of: viewSettings.previewMode) { _, newPreviewMode in
            handlePreviewModeChange(newPreviewMode)
        }
        .onChange(of: viewSettings.libraryLayout) { _, newLibraryLayout in
            handleLibraryLayoutChange(newLibraryLayout)
        }
        .onChange(of: viewMode) { oldMode, newMode in
            handleViewModeChange(old: oldMode, new: newMode)
        }
    }

    /// `navigationSplitColumn` + the SECOND half of the modifier chain.
    /// See `navigationSplitColumn` for why the chain is split.
    @ViewBuilder
    private var decoratedNavigationSplitColumn: some View {
        navigationSplitColumn
            .onChange(of: selectedSidebarItemId) { _, newFolderId in
                handleSidebarSelectionChange(newFolderId)
            }
            .onChange(of: sidebarMode) { _, _ in
                handleSidebarModeChange()
            }
            .onChange(of: showSidebar) { _, _ in
                updateColumnVisibility()
            }
            .onChange(of: columnVisibility) { _, newVisibility in
                handleColumnVisibilityChange(newVisibility)
            }
            .onChange(of: browserSelection) { _, newSelection in
                handleBrowserSelectionChange(newSelection)
            }
            .onChange(of: detailDocument) { _, newDoc in
                handleDetailDocumentChange(newDoc)
            }
            .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
                handleWillTerminate()
            }
            .onReceive(NotificationCenter.default.publisher(for: .ficheroEntitySearchRequested)) { note in
                handleEntitySearchRequested(note)
            }
            .onReceive(NotificationCenter.default.publisher(for: .ficheroOpenClaimSource)) { note in
                handleOpenClaimSource(note)
            }
            .onChange(of: kgFocusState.sourceDocumentId) { _, _ in
                handleKGFocusChanged()
            }
            .onChange(of: kgFocusState.sourcePageLabel) { _, _ in
                handleKGFocusChanged()
            }
            .modifier(
                MainContentModifiers(
                    documentStore: documentStore,
                    workflowStore: workflowStore,
                    conversationService: conversationService,
                    savedSearchService: savedSearchService,
                    appState: appState,
                    sidebarMode: $sidebarMode,
                    viewMode: $viewMode,
                    selectedSidebarItemId: $selectedSidebarItemId,
                    browserSelection: $browserSelection,
                    detailDocument: $detailDocument,
                    columnVisibility: $columnVisibility,
                    editingWorkflow: $editingWorkflow,
                    isDropTargeted: $isDropTargeted,
                    isImporting: $isImporting,
                    importProgress: $importProgress,
                    importError: $importError,
                    handleDocumentChange: handleDocumentChange,
                    handleFileDrop: handleFileDrop
                )
            )
    }
}

// MARK: - Toolbar Content

extension ContentView {
    @ToolbarContentBuilder
    var mainToolbarContent: some ToolbarContent {
        ToolbarItemGroup(placement: .navigation) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    showSidebar.toggle()
                }
            } label: {
                Image(systemName: "sidebar.left")
            }
            .help(showSidebar ? "Hide Sidebar" : "Show Sidebar")

            Button {
                navigateBack()
            } label: {
                Image(systemName: "chevron.left")
            }
            .help("Back (⌘[)")
            .keyboardShortcut("[", modifiers: [.command])
            .disabled(!navigationHistory.canGoBack)

            Button {
                navigateForward()
            } label: {
                Image(systemName: "chevron.right")
            }
            .help("Forward (⌘])")
            .keyboardShortcut("]", modifiers: [.command])
            .disabled(!navigationHistory.canGoForward)
        }

        // Left side: Layout picker, View mode picker, Plus button
        // Conditional based on sidebar mode
        if showNavigationToolbar {
            ToolbarItemGroup(placement: .navigation) {
                // Layout mode picker (None/Standard/Widescreen) - only for modes with preview.
                // Disabled when a folder is the active detail: centerContent forces layout
                // to .none for folders (per #749), so any picker change is a silent no-op.
                // Greyed out makes the dead-state obvious to the user (#787).
                if showLayoutPicker {
                    Picker("Layout", selection: $currentLayoutMode) {
                        ForEach(availableLayoutModes) { mode in
                            Label(mode.rawValue, systemImage: mode.icon)
                                .labelStyle(.iconOnly)
                                .tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)
                    .help("Layout: \(currentLayoutMode.rawValue)")
                    .onChange(of: currentLayoutMode) { _, newMode in
                        withAnimation {
                            // Sync toolbar with View menu previewMode
                            let requestedMode: PreviewMode = switch newMode {
                            case .none: .none
                            case .standard: .standard
                            case .widescreen: .widescreen
                            }
                            viewSettings.previewMode = normalizedPreviewMode(requestedMode)
                        }
                    }
                }

                // Add menu (Plus button)
                AddItemMenu(registry: itemRegistry, style: .button)
                    .help("Add new item (⌘N)")

                if featureManager.isWorkflowsEnabled && featureManager.isWorkflowRunOnSelectionEnabled {
                    // Snapshot selection at Menu-render time so Button actions use
                    // these captured IDs even if focus shifts after the menu opens.
                    // Exclude folder docs — passing a folder ID to the backend expands
                    // it to all children, which is the "On Collection" path, not "On Selection".
                    // In search mode, currentDocuments may be empty (search uses a
                    // separate result set), so a raw browserSelection passes through
                    // unchanged — search results are file docs by construction, not
                    // folders, so the folder-exclusion guard is unnecessary there.
                    let isSearchMode: Bool = {
                        if case .search = viewMode { return true }
                        return false
                    }()
                    let capturedSelectionIds: [String] = !browserSelection.isEmpty
                        ? (isSearchMode
                            ? Array(browserSelection)
                            : browserSelection.filter { id in
                                documentStore.currentDocuments.first { $0.id == id }?.docType != .folder
                            })
                        : (detailDocument.flatMap { $0.docType == .folder ? nil : [$0.id] } ?? [])
                    let collectionFiles = documentStore.currentDocuments.filter { $0.docType == .file }
                    let hasCollection = !collectionFiles.isEmpty
                    let sortedWorkflows = workflowStore.workflows.sorted {
                        $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
                    }
                    Menu {
                        if workflowStore.workflows.isEmpty {
                            Text("No workflows available")
                        } else {
                            if !capturedSelectionIds.isEmpty {
                                Section("On Selection") {
                                    ForEach(sortedWorkflows, id: \.id) { workflow in
                                        Menu(workflow.name) {
                                            Button("Default") {
                                                runWorkflowOnSelection(
                                                    workflowId: workflow.id,
                                                    preselectedIds: capturedSelectionIds
                                                )
                                            }
                                            ForEach(workflowRunProviderCache.providers.filter { $0.available }) { provider in
                                                if provider.models.isEmpty {
                                                    Button(provider.name) {
                                                        runWorkflowOnSelection(
                                                            workflowId: workflow.id,
                                                            preselectedIds: capturedSelectionIds,
                                                            providerOverride: provider.id
                                                        )
                                                    }
                                                } else {
                                                    Menu(provider.name) {
                                                        ForEach(provider.models, id: \.self) { model in
                                                            Button(model) {
                                                                runWorkflowOnSelection(
                                                                    workflowId: workflow.id,
                                                                    preselectedIds: capturedSelectionIds,
                                                                    providerOverride: provider.id,
                                                                    modelOverride: model
                                                                )
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            if hasCollection {
                                Section("On Collection (\(collectionFiles.count))") {
                                    ForEach(sortedWorkflows, id: \.id) { workflow in
                                        Menu(workflow.name) {
                                            Button("Default") {
                                                runWorkflowOnCollection(workflowId: workflow.id)
                                            }
                                            ForEach(workflowRunProviderCache.providers.filter { $0.available }) { provider in
                                                if provider.models.isEmpty {
                                                    Button(provider.name) {
                                                        runWorkflowOnCollection(
                                                            workflowId: workflow.id,
                                                            providerOverride: provider.id
                                                        )
                                                    }
                                                } else {
                                                    Menu(provider.name) {
                                                        ForEach(provider.models, id: \.self) { model in
                                                            Button(model) {
                                                                runWorkflowOnCollection(
                                                                    workflowId: workflow.id,
                                                                    providerOverride: provider.id,
                                                                    modelOverride: model
                                                                )
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            if capturedSelectionIds.isEmpty && !hasCollection {
                                Text("Select a document or open a collection")
                                    .foregroundStyle(.secondary)
                            }
                        }
                    } label: {
                        Label("Run Workflow", systemImage: "play.square.stack")
                    }
                    .onAppear {
                        Task { @MainActor in
                            await workflowRunProviderCache.ensureLoaded(
                                chatService: LibraryManager.shared.globalLibrary?.chatServiceGenerated
                            )
                        }
                    }
                    .help("Run Workflow on Selection or Collection")
                    .disabled(
                        workflowStore.workflows.isEmpty
                        || (capturedSelectionIds.isEmpty && !hasCollection)
                    )
                }
            }
        }

        // Search entry point lives in the system .searchable modifier
        // applied to mainContentView (below). On macOS that renders as
        // a Finder-style magnifying-glass that expands to a search
        // field — placed by the system to the right of the trailing
        // toolbar items. We keep it system-rendered (one consistent
        // bar) instead of having a custom .principal field competing
        // with SearchView's own .searchable.

        // Document grid toggle — hides/shows the icon-grid/list middle column
        // so the preview pane can fill the full content area (#616).
        ToolbarItem(placement: .automatic) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    showDocumentGrid.toggle()
                }
            } label: {
                Image(systemName: showDocumentGrid ? "rectangle.split.2x1" : "rectangle")
            }
            .help(showDocumentGrid ? "Hide Document Grid (⌘⇧G)" : "Show Document Grid (⌘⇧G)")
            .keyboardShortcut("g", modifiers: [.command, .shift])
        }

        // Inspector toggle at the trailing edge of the toolbar — the
        // Finder/Notes/Xcode convention (#1229 part 1). Uses
        // `sidebar.right` to match the View-menu InspectorButton; the
        // old `info.circle` collided with the inspector's own Info-tab
        // icon and read as "info" rather than "inspector".
        // The ⌘⌥I shortcut is owned by the View-menu command
        // (ViewMenuCommands.InspectorButton) — not re-bound here to
        // avoid a duplicate key binding.
        // NOTE: a true window-corner placement (flush with the window's
        // trailing edge, over the inspector pane) is deferred — the
        // inspector is a window-level HStack sibling of
        // NavigationSplitView (#1199), so the unified toolbar can't span
        // it without the #1199 window-layout rework.
        if showInspectorToggle {
            ToolbarItem(placement: .automatic) {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        showInspectorSidebar.toggle()
                    }
                } label: {
                    Image(systemName: "sidebar.right")
                }
                .help(showInspectorSidebar ? "Hide Inspector (⌘⌥I)" : "Show Inspector (⌘⌥I)")
            }
        }
    }
}

// MARK: - Preview
#Preview("Library Mode") {
    ContentView()
        .environmentObject(ViewSettings())
        .environmentObject(AppState())
        .frame(width: 1200, height: 700)
}
