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
    static let sidebarMinWidth: Double = 180
    static let inspectorMinWidth: Double = 250
    static let inspectorMaxWidth: Double = 1000
    static let contentMinWidth: Double = 520
    static let contentMaxWidth: Double = 2200
    /// Minimum width of the widescreen content-list pane. Clamped to the
    /// view-mode icon rail width so the rail and list rows (thumbnail + text)
    /// can't be dragged narrow enough to clip (#1243). The sort/filter tools
    /// now overflow into a trailing menu when the rail gets tight (#1733), so
    /// the list can shrink far enough to let the adaptive thumbnail grid fall
    /// to a single column again (#1734).
    static let contentListMinWidth: Double = 220
    /// Minimum width of the flexible PDF canvas pane so its mini-toolbar
    /// (zoom −/%/+, fit, actual-size, magnifier, loupe + two dividers) never
    /// clips when the reading-surface dividers are dragged inward. The
    /// resizable neighbours are already clamped by their ResizableDividers;
    /// this guards the one `.frame(maxWidth: .infinity)` pane that otherwise
    /// has no floor. (#1454)
    static let pdfCanvasMinWidth: Double = 360
    static let readingPaneMinWidth: Double = 220

    // MARK: - Environment

    @EnvironmentObject var viewSettings: ViewSettings
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var apiClient: APIClient
    @Environment(DocumentStore.self) var documentStore: DocumentStore
    @EnvironmentObject var conversationService: ConversationServiceGenerated
    @EnvironmentObject var importService: ImportServiceGenerated
    @EnvironmentObject var windowState: WindowState
    @Environment(WorkflowStore.self) var workflowStore
    @EnvironmentObject var savedSearchService: SavedSearchServiceGenerated
    @EnvironmentObject var workflowStreamService: WorkflowStreamService
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    @Environment(KGFocusState.self) var kgFocusState
    @Environment(\.openWindow) var openWindow
    @EnvironmentObject var claimFocusState: ClaimFocusState
    @EnvironmentObject var researchService: ResearchService

    // MARK: - State (synced with @SceneStorage for persistence)

    // Runtime state - full objects for use in views
    @State var viewMode: AppViewMode = .library(nil)
    @State var detailDocument: Document?
    /// The page document currently in view, updated only by scroll/page-flip
    /// events. Drives the inspector without re-rooting the WebKit pane (#1463).
    @State var pageFocusDocument: Document?
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
    // Per-window visibility of the three middle panes (#1448). Each window
    // keeps its own choice via @SceneStorage (same pattern as the
    // sidebar/inspector toggles), so selection never remounts or hides panes.
    @SceneStorage("showDocumentCanvas") var showDocumentCanvas: Bool = true
    @SceneStorage("showReadingPane") var showReadingPane: Bool = true
    // When false (default), selecting a different item NEVER changes which
    // panes are visible — a folder shows the same panes as a PDF. The visible
    // pane set is the user's choice (the toggles above). Opt in to the old
    // selection-driven behaviour (e.g. folders collapse the preview) by
    // turning this on. App-wide preference, toggled from the View menu. (#1452)
    @AppStorage("layout.followsSelection") var layoutFollowsSelection: Bool = false
    // Library sort field / direction / filter-bar visibility, lifted out of
    // LibraryView's @State so the in-content mode rail can host the Sort + Filter
    // controls at the Library view's top-right (#1477).
    @StateObject var libraryToolbarState = LibraryToolbarState()

    // Map view persistence (latitude, longitude, zoom)
    @SceneStorage("mapLatitude") var mapLatitude: Double = 0.0
    @SceneStorage("mapLongitude") var mapLongitude: Double = 0.0
    @SceneStorage("mapZoom") var mapZoom: Double = 1.0
    @SceneStorage("sidebarWindowPersistenceId") var sidebarWindowPersistenceId: String = UUID().uuidString

    // Per-folder view mode persistence (JSON-encoded [folderId: displayMode.rawValue], per-window)
    @SceneStorage("folderViewDisplayModes") var folderViewDisplayModesJSON: String = "{}"

    @StateObject var itemRegistry = ItemTypeRegistry()
    @StateObject var performanceService = PerformanceService()
    @State var documentScrollSync = DocumentScrollSyncState()
    @State var toolbarSearchText: String = ""
    @State var navigationHistory = AppNavigationHistory()
    @State var isRestoringNavigationHistory = false

    // Error service (using singleton pattern)
    @ObservedObject var errorService = ErrorService.shared
    @ObservedObject var featureManager = FeatureManager.shared
    @ObservedObject var workflowRunProviderCache = WorkflowRunProviderCache.shared

    // Pane focus state for Tab cycling
    @FocusState var focusedPane: PaneFocus?

    // Contextual Delete action published by the focused LibraryView
    // (`\.libraryDeleteSelection`). It is non-nil only when a deletable
    // selection exists, so the zoned-toolbar Delete button reflects selection
    // for free (disabled when nil) — reusing the existing delete action +
    // confirmation rather than reimplementing it (#2032).
    @FocusedValue(\.libraryDeleteSelection) var libraryDeleteSelection

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
        // Inspector is a NATIVE SwiftUI `.inspector()` column attached to the
        // NavigationSplitView, so it persists across all view modes (#1199) AND
        // the unified window toolbar/title spans it correctly — trailing toolbar
        // items sit above the inspector instead of the toolbar overrunning it
        // (#2033). It replaced the former window-level HStack sibling, which
        // macOS painted the toolbar across (the bug Daniel saw).
        //
        // The split-view column itself carries a very long chained-modifier
        // list (toolbar + ~16 .onChange/.onReceive handlers). To keep any single
        // `some View` expression inside the Swift type-checker's complexity
        // budget, that chain is broken across two intermediate properties:
        // `navigationSplitColumn` (NavigationSplitView + first half of modifiers)
        // and `decoratedNavigationSplitColumn` (the remaining modifiers).
        decoratedNavigationSplitColumn
            .inspector(isPresented: $showInspectorSidebar) {
                detailView
                    .inspectorColumnWidth(
                        min: CGFloat(ContentView.inspectorMinWidth),
                        ideal: 300,
                        max: CGFloat(ContentView.inspectorMaxWidth)
                    )
            }
            .frame(minWidth: CGFloat(paneAwareWindowMinWidth), maxWidth: .infinity, maxHeight: .infinity)

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
                // The detail column carries only a MODEST hard floor — the
                // always-present library-list spine width — NOT the full
                // per-layout `paneAwareDetailMinWidth`. The full content
                // reservation lives on the window-min frame in `mainContentView`
                // (sidebar + detail). Pinning the FULL detail min here made
                // NavigationSplitView sacrifice the SIDEBAR (whose column min
                // yields first under pressure) whenever the window narrowed below
                // sidebar+detail — the sidebar collapsed/disappeared. With a small
                // floor the sidebar always keeps its `.navigationSplitViewColumnWidth`
                // min and the CONTENT shrinks/scrolls instead (frame ① bug-fix).
                .frame(minWidth: CGFloat(ContentView.contentListMinWidth), maxWidth: .infinity)
                // Publish the per-window inspector binding from the detail
                // column (always present) rather than the sidebar, which leaves
                // the hierarchy when collapsed and made ⌘⌥I no-op (#1513/#1451).
                .focusedSceneValue(\.showInspector, $showInspectorSidebar)
                // Publish the reading-surface pane toggles so the View menu can
                // mirror the toolbar buttons for each pane (#1215).
                .focusedSceneValue(\.showDocumentGrid, $showDocumentGrid)
                .focusedSceneValue(\.showDocumentCanvas, $showDocumentCanvas)
                .focusedSceneValue(\.showReadingPane, $showReadingPane)
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
        // Inspector visibility is per-window (@SceneStorage). It is NOT mirrored
        // into the app-wide ViewSettings any more — doing so flipped the
        // inspector in every open window at once (#1451). The View menu reaches
        // this window's state through FocusedValues.showInspector instead.
        .onChange(of: showInspectorSidebar) { _, _ in
            updateColumnVisibility()
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
            .onChange(of: viewDisplayMode) { _, newMode in
                handleViewDisplayModeChange(newMode)
            }
            .onChange(of: workflowStore.changeToken) { _, _ in
                Task { await workflowStore.loadWorkflows() }
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
    @ViewBuilder
    private func toolbarToggleIcon(_ systemName: String, isActive: Bool) -> some View {
        Image(systemName: systemName)
            .symbolVariant(isActive ? .fill : .none)
    }

    // MARK: Zoned toolbar (Mail-style)
    //
    // The window toolbar is organised into ACTION zones separated by flexible
    // spacers, modelled on Apple Mail (#2032). Presentation controls ("how it's
    // shown" — layout/view-mode pickers, library/canvas/reading pane toggles)
    // do NOT live here; they are in the View menu (ViewMenuCommands:
    // LibraryLayoutSection / PreviewModeSection / PaneVisibilitySection). The
    // main toolbar is verbs only.
    //
    // `mainToolbarContent` is a thin dispatcher to three bounded
    // `@ToolbarContentBuilder` sub-properties so no single builder grows large
    // enough to risk a type-check timeout.
    @ToolbarContentBuilder
    var mainToolbarContent: some ToolbarContent {
        // Mode icon + title in toolbar center — updates on every sidebar/view-mode change (#323).
        // @ToolbarContentBuilder has no view-chain budget limit, so Label compiles cleanly here.
        ToolbarItem(placement: .principal) {
            Label(toolbarTitle, systemImage: toolbarIcon)
                .labelStyle(.titleAndIcon)
                .font(.headline)
        }

        // LEADING zone — panel toggles (Xcode/Finder convention): sidebar + history.
        leadingToolbarContent

        ToolbarSpacer(.flexible)

        // CONTENT zone — the action verbs: New/Import, Delete, Run Workflow.
        contentToolbarContent

        ToolbarSpacer(.flexible)

        // TRAILING zone — inspector toggle.
        trailingToolbarContent
    }

    /// LEADING zone: sidebar toggle + back/forward history. Panel toggles grouped
    /// at the window's leading edge (Xcode-style).
    @ToolbarContentBuilder
    private var leadingToolbarContent: some ToolbarContent {
        ToolbarItemGroup(placement: .navigation) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    showSidebar.toggle()
                }
            } label: {
                toolbarToggleIcon("sidebar.left", isActive: showSidebar)
            }
            .help(showSidebar ? "Hide Sidebar" : "Show Sidebar")

            Button {
                navigateBack()
            } label: {
                Image(systemName: "chevron.backward")
            }
            .help("Back (⌘[)")
            .keyboardShortcut("[", modifiers: [.command])
            .disabled(!navigationHistory.canGoBack)

            Button {
                navigateForward()
            } label: {
                Image(systemName: "chevron.forward")
            }
            .help("Forward (⌘])")
            .keyboardShortcut("]", modifiers: [.command])
            .disabled(!navigationHistory.canGoForward)
        }
    }

    /// CONTENT zone: the ACTION verbs. New/Import (＋ Add menu), Delete (contextual,
    /// reflects selection), Run Workflow. Presentation pickers/pane-toggles that
    /// used to sit here have moved to the View menu (#2032).
    @ToolbarContentBuilder
    private var contentToolbarContent: some ToolbarContent {
        if showNavigationToolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                // Add menu (Plus button) — New / Import.
                AddItemMenu(registry: itemRegistry, style: .button)
                    .help("Add new item (⌘N)")

                // Delete — contextual. Reuses the existing delete action +
                // confirmation published by the focused LibraryView
                // (`\.libraryDeleteSelection`); the focused value is non-nil only
                // when a deletable selection exists, so the button disables itself
                // when there is nothing to delete (#2032).
                Button(role: .destructive) {
                    libraryDeleteSelection?()
                } label: {
                    Image(systemName: "trash")
                }
                .help("Delete Selection")
                .disabled(libraryDeleteSelection == nil)

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
    }

    /// TRAILING zone: inspector toggle. Finder/Notes/Xcode convention (#1229 part 1).
    ///
    /// The presentation pane toggles (Library Browser / Document Canvas / Reading
    /// Pane) and the layout / view-mode pickers that previously lived in the
    /// toolbar have moved OUT of the action toolbar — they are "how it's shown",
    /// not verbs. Their controls already exist in the View menu
    /// (ViewMenuCommands.PaneVisibilitySection — ⌘⇧G for the browser; and
    /// LibraryLayoutSection / PreviewModeSection for the pickers), so removing
    /// the toolbar duplicates loses nothing (#2032 / #1215).
    @ToolbarContentBuilder
    private var trailingToolbarContent: some ToolbarContent {
        // Uses `sidebar.right` to match the View-menu InspectorButton; the
        // old `info.circle` collided with the inspector's own Info-tab icon.
        // The ⌘⌥I shortcut is owned by the View-menu command
        // (ViewMenuCommands.InspectorButton) — not re-bound here to avoid a
        // duplicate key binding.
        if showInspectorToggle {
            ToolbarItem(placement: .automatic) {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        showInspectorSidebar.toggle()
                    }
                } label: {
                    toolbarToggleIcon("sidebar.right", isActive: showInspectorSidebar)
                }
                .help(showInspectorSidebar ? "Hide Inspector (⌘⌥I)" : "Show Inspector (⌘⌥I)")
            }
        }
    }
}

// NOTE — content-side SEARCH (deferred). Search stays on the per-mode system
// `.searchable(placement: .toolbar)` owned by LibraryView/SearchView inside the
// NavigationSplitView detail (each with its own `$toolbarQuery` +
// `onToolbarSearchSubmit` wiring — one per mode, to avoid the NSToolbar
// duplicate-identifier crash). macOS renders one unified NSToolbar per window
// and paints the system search field at the far trailing edge (above the
// `.inspector()` column). Replacing `.searchable` with a custom content-zone
// `ToolbarItem` holding a search field bound to `$toolbarQuery` would risk the
// documented duplicate-identifier crash and break the per-mode submit wiring,
// so content-side search is intentionally deferred (smallest correct change).

// MARK: - Preview
#Preview("Library Mode") {
    ContentView()
        .environmentObject(ViewSettings())
        .environmentObject(AppState())
        .frame(width: 1200, height: 700)
}
