import OSLog
import SwiftUI
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "com.fichero.fichero", category: "ContentView")
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
    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding: Bool = false
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
    @State var toolbarSearchText: String = ""
    @State var navigationHistory = AppNavigationHistory()
    @State var isRestoringNavigationHistory = false

    // Error service (using singleton pattern)
    @ObservedObject var errorService = ErrorService.shared
    @ObservedObject var featureManager = FeatureManager.shared

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
            get: { appState.isBackendRunning && !hasCompletedOnboarding },
            set: { if !$0 { hasCompletedOnboarding = true } }
        )) {
            // First-launch wizard. Lives in App/WelcomeView.swift to avoid a
            // pbxproj edit. Gate is the @AppStorage flag the wizard sets when
            // the user finishes (or skips with "Set up later"). Backend must
            // be running because the wizard calls /api/providers to save the
            // user's pick.
            OnboardingWizardView()
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
        HStack(spacing: 0) {
            NavigationSplitView(columnVisibility: $columnVisibility) {
                sidebarContent
            } detail: {
                centerContent
                    .frame(minWidth: CGFloat(ContentView.contentMinWidth), maxWidth: .infinity)
            }
            // Avoid duplicate generic per-column title pills in macOS split view.
            .navigationTitle(toolbarTitle)
            .toolbar(removing: .sidebarToggle)
            .onAppear {
                // Restore all persisted state from @SceneStorage
                restorePersistedState()
                if focusedPane == nil {
                    focusedPane = .content
                }
                // Clamp to a sane range. SceneStorage can hold stale/corrupted values
                // from previous sessions (e.g., values written during layout animations).
                // 400 is a generous practical maximum for an inspector panel.
                inspectorWidth = min(max(inspectorWidth, ContentView.inspectorMinWidth), 400)
                contentWidth = min(
                    max(contentWidth, ContentView.contentMinWidth),
                    ContentView.contentMaxWidth
                )
                if !featureManager.isSearchEnabled && sidebarMode == .search {
                    sidebarMode = .library
                    viewMode = .library(nil)
                }
                // Sync View menu inspector command to per-window inspector state.
                if viewSettings.showInspector != showInspectorSidebar {
                    viewSettings.showInspector = showInspectorSidebar
                }
                updateColumnVisibility()
                viewDisplayMode = normalizedViewDisplayMode(viewDisplayMode)
                viewSettings.previewMode = normalizedPreviewMode(viewSettings.previewMode)
                let initialLayoutMode: LayoutMode = switch viewSettings.previewMode {
                case .none: .none
                case .standard: .standard
                case .widescreen: .widescreen
                }
                if currentLayoutMode != initialLayoutMode {
                    currentLayoutMode = initialLayoutMode
                }

                // If documents were already loaded before onAppear, restore
                // the preview selection now (the onChange handler won't fire).
                if detailDocument == nil, !documentStore.currentDocuments.isEmpty {
                    let firstSelectedId = browserSelection.first
                    if let firstSelectedId {
                        detailDocument = documentStore.currentDocuments.first(where: { $0.id == firstSelectedId })
                    }
                }
                recordNavigationEntry()
            }
            .onChange(of: documentStore.collections) { oldCollections, newCollections in
                // Re-restore view mode once data loads (collections arrive after API responds)
                guard oldCollections.isEmpty, !newCollections.isEmpty else { return }
                viewMode = restoreViewMode(type: storedViewModeType, itemId: storedViewModeItemId)
                let restoredId = sidebarSelectionId(
                    for: storedViewModeType,
                    itemId: storedViewModeItemId
                )
                // sidebarSelectionId returns nil for "activity" with no run ID; use the
                // fixed tag so the Activity row stays highlighted after relaunch (#648).
                selectedSidebarItemId = restoredId ?? (storedViewModeType == "activity" ? "activity-browser" : nil)
            }
            .onChange(of: documentStore.currentDocuments) { _, newDocs in
                // Populate preview from restored selection whenever documents load
                if detailDocument == nil,
                   let firstSelectedId = browserSelection.first,
                   let doc = newDocs.first(where: { $0.id == firstSelectedId }) {
                    detailDocument = doc
                }
                // Keep detailDocument in sync when currentDocuments refreshes
                // so the inspector shows updated page_content after workflows complete.
                if let currentDetail = detailDocument,
                   let updatedDoc = newDocs.first(where: { $0.id == currentDetail.id }) {
                    detailDocument = updatedDoc
                }
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
            .toolbar {
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
                            let folderActive = detailDocument?.docType == .folder
                            Picker("Layout", selection: $currentLayoutMode) {
                                ForEach(availableLayoutModes) { mode in
                                    Label(mode.rawValue, systemImage: mode.icon)
                                        .labelStyle(.iconOnly)
                                        .tag(mode)
                                }
                            }
                            .pickerStyle(.segmented)
                            .help(folderActive
                                    ? "Folder selected — preview pane disabled"
                                    : "Layout: \(currentLayoutMode.rawValue)")
                            .disabled(folderActive)
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
                                                Button(workflow.name) {
                                                    runWorkflowOnSelection(
                                                        workflowId: workflow.id,
                                                        preselectedIds: capturedSelectionIds
                                                    )
                                                }
                                            }
                                        }
                                    }
                                    if hasCollection {
                                        Section("On Collection (\(collectionFiles.count))") {
                                            ForEach(sortedWorkflows, id: \.id) { workflow in
                                                Button(workflow.name) {
                                                    runWorkflowOnCollection(workflowId: workflow.id)
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
            .onChange(of: viewSettings.previewMode) { _, newPreviewMode in
                // Sync View menu changes back to toolbar layout picker
                let effectivePreviewMode = normalizedPreviewMode(newPreviewMode)
                if effectivePreviewMode != newPreviewMode {
                    viewSettings.previewMode = effectivePreviewMode
                }

                let newLayoutMode = switch effectivePreviewMode {
                case .none: LayoutMode.none
                case .standard: LayoutMode.standard
                case .widescreen: LayoutMode.widescreen
                }

                if currentLayoutMode != newLayoutMode {
                    withAnimation {
                        currentLayoutMode = newLayoutMode
                    }
                }
            }
            .onChange(of: viewSettings.libraryLayout) { _, newLibraryLayout in
                // Sync View menu changes back to toolbar view mode picker
                let newDisplayMode = switch newLibraryLayout {
                case .icons: ViewDisplayMode.icon
                case .list: ViewDisplayMode.list
                case .table: ViewDisplayMode.table
                case .map: ViewDisplayMode.map
                }
                let effectiveDisplayMode = normalizedViewDisplayMode(newDisplayMode)

                if effectiveDisplayMode != newDisplayMode {
                    viewSettings.libraryLayout = switch effectiveDisplayMode {
                    case .icon: .icons
                    case .list: .list
                    case .table: .table
                    case .map: .map
                    }
                }

                if viewDisplayMode != effectiveDisplayMode {
                    viewDisplayMode = effectiveDisplayMode
                }
            }
            .onChange(of: viewMode) { oldMode, newMode in
                guard !isRestoringNavigationHistory else { return }
                // Auto-save only when leaving the currently edited workflow.
                // Skip workflow->same-workflow transitions (e.g., sidebar rename refresh),
                // which can otherwise overwrite a fresh rename with stale editor state.
                let shouldAutoSaveWorkflow: Bool = {
                    guard case .workflow(let oldWorkflow) = oldMode, let oldWorkflow else {
                        return false
                    }

                    switch newMode {
                    case .workflow(let newWorkflow):
                        guard let newWorkflow else {
                            return false
                        }
                        return newWorkflow.id != oldWorkflow.id
                    default:
                        return true
                    }
                }()

                if shouldAutoSaveWorkflow, case .workflow(let oldWorkflow) = oldMode, let workflow = oldWorkflow {
                    // Capture the editing workflow content before it changes
                    let workflowToSave = editingWorkflow
                    Task { @MainActor in
                        await autoSaveWorkflow(workflowId: workflow.id, workflow: workflowToSave)
                    }
                }

                // Persist view mode to @SceneStorage
                let (type, id) = serializeViewMode(newMode)
                storedViewModeType = type
                storedViewModeItemId = id
                recordNavigationEntry()
            }
            .onChange(of: selectedSidebarItemId) { _, newFolderId in
                if isRestoringNavigationHistory { return }
                // Restore per-folder view mode when switching folders.
                // Priority: per-folder save > global default > current
                // SceneStorage value. The global default protects against
                // the "revert to Icon when no per-folder save exists"
                // complaint in #943.
                if let saved = displayMode(for: newFolderId) {
                    viewDisplayMode = normalizedViewDisplayMode(saved)
                } else {
                    let normalizedDefault = normalizedViewDisplayMode(defaultLibraryViewDisplayMode)
                    if viewDisplayMode != normalizedDefault {
                        viewDisplayMode = normalizedDefault
                    }
                }

                // Clear grid selection on sidebar folder change so the folder
                // inspector shows by default. Without this, a stale browserSelection
                // from a previous folder can resolve to a child of the new folder
                // (when ids happen to be present in the new folder's children),
                // suppressing the folder inspector. (#712)
                browserSelection.removeAll()

                // Drive the inspector from sidebar selection so clicking a folder
                // (or any document row) in the sidebar populates the inspector.
                // Sidebar IDs are prefixed "doc:UUID" — extract the bare doc ID
                // before looking up. (#696 — folder inspector blank after sidebar
                // click. MEMORY: SidebarItem.id is 'doc:UUID', strip prefix.)
                guard let prefixedId = newFolderId,
                      prefixedId.hasPrefix("doc:") else { return }
                let docId = String(prefixedId.dropFirst("doc:".count))
                // Force-clear any previewed document immediately so the inspector
                // reflects the newly-selected folder before the async applyDoc
                // resolution completes. Without this, detailDocument stays set to
                // the previously-previewed file and inspectorDocument step 1 can
                // match it against the stale browserSelection. (#795)
                detailDocument = nil
                // Closure to apply a resolved Document — sets detailDocument and,
                // for folders, collapses the preview pane so navigating in the
                // sidebar lands on a clean grid view (#785 follow-up). Daniel's
                // mental model: "click sidebar to browse, click doc in grid to
                // preview." Folders shouldn't be previewed; clicking a folder
                // should reset the layout to grid-only.
                let applyDoc: (Document) -> Void = { doc in
                    // Defer mutations to next run loop turn to avoid triggering
                    // multiple FocusedValue updates in the same render cycle (#961).
                    DispatchQueue.main.async {
                        detailDocument = doc
                        if doc.docType == .folder, currentLayoutMode != .none {
                            currentLayoutMode = .none
                            viewSettings.previewMode = .none
                        }
                    }
                }
                if detailDocument?.id != docId {
                    if let doc = documentStore.currentDocuments.first(where: { $0.id == docId }) {
                        applyDoc(doc)
                    } else {
                        Task { @MainActor in
                            let fetched: Document? = try? await documentStore.api.get(
                                "/documents/\(docId)"
                            )
                            if let fetched, selectedSidebarItemId == prefixedId {
                                applyDoc(fetched)
                            }
                        }
                    }
                } else if let existing = detailDocument,
                          existing.docType == .folder,
                          currentLayoutMode != .none {
                    // Re-clicking the already-selected folder: still collapse the
                    // preview. Earlier guard short-circuits the detailDocument
                    // assignment so we have to handle this branch explicitly.
                    DispatchQueue.main.async {
                        currentLayoutMode = .none
                        viewSettings.previewMode = .none
                    }
                }
            }
            .onChange(of: sidebarMode) { _, _ in
                viewDisplayMode = normalizedViewDisplayMode(viewDisplayMode)
                viewSettings.libraryLayout = switch viewDisplayMode {
                case .icon: .icons
                case .list: .list
                case .table: .table
                case .map: .map
                }

                let effectivePreviewMode = normalizedPreviewMode(viewSettings.previewMode)
                if effectivePreviewMode != viewSettings.previewMode {
                    viewSettings.previewMode = effectivePreviewMode
                }

                let effectiveLayoutMode: LayoutMode = switch effectivePreviewMode {
                case .none: .none
                case .standard: .standard
                case .widescreen: .widescreen
                }
                if currentLayoutMode != effectiveLayoutMode {
                    currentLayoutMode = effectiveLayoutMode
                }
            }
            .onChange(of: showSidebar) { _, _ in
                updateColumnVisibility()
            }
            .onChange(of: columnVisibility) { _, newVisibility in
                // Persist column visibility to @SceneStorage
                // Map NavigationSplitViewVisibility to raw int for @SceneStorage
                if newVisibility == .automatic {
                    columnVisibilityRaw = 0
                } else if newVisibility == .detailOnly {
                    columnVisibilityRaw = 1
                } else if newVisibility == .all {
                    columnVisibilityRaw = 2
                } else if newVisibility == .doubleColumn {
                    columnVisibilityRaw = 3
                } else {
                    columnVisibilityRaw = 0
                }

                // Keep explicit left-sidebar state in sync with split-view visibility.
                // In this app's layout, `.doubleColumn` is sidebar + content.
                if newVisibility == .detailOnly {
                    showSidebar = false
                } else if newVisibility == .all || newVisibility == .doubleColumn || newVisibility == .automatic {
                    showSidebar = true
                }
            }
            .onChange(of: browserSelection) { _, newSelection in
                // Persist browser selection to @SceneStorage
                if let encoded = try? JSONEncoder().encode(newSelection) {
                    browserSelectionData = encoded
                }
                // Note: previously this auto-synced detailDocument from selection
                // so single-clicks in the grid would swap the preview pane. Per
                // Daniel's intended click model (#772): single-click should only
                // update the right inspector (via inspectorDocument's
                // browserSelection priority), NOT the preview pane. detailDocument
                // is now only mutated by handleDoubleClick (and explicit
                // openSelectedDocument keyboard shortcut + sidebar selection).
            }
            .onChange(of: detailDocument) { _, newDoc in
                // Keep documentStore.selectedDocument in sync so WorkflowEditor
                // toolbar button sees the current document at run time.
                documentStore.selectedDocument = newDoc
                guard !isRestoringNavigationHistory else { return }
                recordNavigationEntry()
            }
            .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
                // Auto-save workflow when app quits
                if case .workflow(let workflow) = viewMode, let workflowItem = workflow {
                    let workflowToSave = editingWorkflow
                    Task { @MainActor in
                        await autoSaveWorkflow(workflowId: workflowItem.id, workflow: workflowToSave)
                    }
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: .ficheroEntitySearchRequested)) { note in
                // Click on a blue entity lozenge anywhere in the UI fires the
                // toolbar search for that name. Same code path as typing in
                // the toolbar — creates a saved search, switches to search
                // mode, runs the query.
                //
                // When the lozenge knows its entity_type (people / places /
                // keywords / etc.), we construct a SCOPED query like
                // `keywords:"social license"` so the search hits only that
                // artifact type — exactly the docs the user is asking about.
                // Free-text fallback when the type isn't tagged so older
                // call sites still work.
                guard let name = note.userInfo?["name"] as? String,
                      !name.trimmingCharacters(in: .whitespaces).isEmpty else { return }
                let entityType = note.userInfo?["entityType"] as? String
                let query: String
                if let entityType, !entityType.isEmpty {
                    let needsQuoting = name.contains(" ")
                    query = needsQuoting
                        ? "\(entityType):\"\(name)\""
                        : "\(entityType):\(name)"
                } else {
                    query = name
                }
                toolbarSearchText = query
                runToolbarSearch(query)
            }
            .onReceive(NotificationCenter.default.publisher(for: .ficheroOpenClaimSource)) { note in
                // Claim card source-doc link → navigate to the document
                // with the page scrolled into view. userInfo carries
                // documentId (required) + pageLabel / charStart / charEnd /
                // claimId (all optional). For now this lights up doc
                // selection + posts an internal navigation event the
                // PDF preview will consume to scroll to pageLabel. The
                // highlight-span overlay lands in a later phase (#995). (#978/#979/#982)
                guard let info = note.userInfo,
                      let docId = info["documentId"] as? String else { return }
                // Switch to library view if we're in another mode (KG /
                // Activity / Workflow) — the source preview lives there.
                if sidebarMode != .library {
                    sidebarMode = .library
                }
                showInspectorSidebar = true
                focusedPane = .inspector
                if let claimId = info["claimId"] as? String {
                    claimFocusState.selectClaim(
                        claimId: claimId,
                        claimText: (info["claimText"] as? String) ?? (info["excerpt"] as? String),
                        sourceDocumentId: docId,
                        pageLabel: info["pageLabel"] as? String,
                        charStart: info["charStart"] as? Int,
                        charEnd: info["charEnd"] as? Int
                    )
                }
                // Resolve page-child source documents to their parent file and
                // select it. Then forward the page-navigation request that
                // PDFPageView consumes for scrolling/highlighting.
                Task { @MainActor in
                    await navigateToSourcePage(docId)
                    NotificationCenter.default.post(
                        name: .ficheroNavigateToPage,
                        object: nil,
                        userInfo: info
                    )
                }
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
}

// MARK: - Preview
#Preview("Library Mode") {
    ContentView()
        .environmentObject(ViewSettings())
        .environmentObject(AppState())
        .frame(width: 1200, height: 700)
}
