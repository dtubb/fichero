import OSLog
import SwiftUI
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "ContentView")
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
    @SceneStorage("currentLayoutMode") var currentLayoutMode: LayoutMode = .widescreen
    @SceneStorage("sidebarMode") var sidebarMode: SidebarMode = .library

    // Column visibility persistence
    @SceneStorage("sidebarWidth") var sidebarWidth: Double = 280
    @SceneStorage("contentWidth") var contentWidth: Double = 600
    @SceneStorage("inspectorWidth") var inspectorWidth: Double = 300
    @SceneStorage("widescreenContentPaneWidth") var widescreenContentPaneWidth: Double = 320
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
        .onKeyPress(.leftArrow, phases: .down) { keyPress in
            guard keyPress.modifiers.contains(.option) else { return .ignored }
            cyclePaneFocus(reverse: true)
            return .handled
        }
        .onKeyPress(.rightArrow, phases: .down) { keyPress in
            guard keyPress.modifiers.contains(.option) else { return .ignored }
            cyclePaneFocus(reverse: false)
            return .handled
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
        NavigationSplitView(columnVisibility: $columnVisibility) {
            sidebarContent
        } detail: {
            HStack(spacing: 0) {
                centerContent
                    .frame(minWidth: CGFloat(ContentView.contentMinWidth), maxWidth: .infinity)
                if showInspectorSidebar {
                    ResizableDivider(
                        width: $inspectorWidth,
                        minWidth: ContentView.inspectorMinWidth,
                        maxWidth: ContentView.inspectorMaxWidth
                    )
                    detailView
                        .frame(width: CGFloat(inspectorWidth))
                }
            }
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
                if let firstSelectedId = browserSelection.first,
                   let doc = documentStore.currentDocuments.first(where: { $0.id == firstSelectedId }) {
                    detailDocument = doc
                }
            }
        }
        .onChange(of: documentStore.collections) { oldCollections, newCollections in
            // Re-restore view mode once data loads (collections arrive after API responds)
            guard oldCollections.isEmpty, !newCollections.isEmpty else { return }
            viewMode = restoreViewMode(type: storedViewModeType, itemId: storedViewModeItemId)
            selectedSidebarItemId = sidebarSelectionId(
                for: storedViewModeType,
                itemId: storedViewModeItemId
            )
        }
        .onChange(of: documentStore.currentDocuments) { _, newDocs in
            // Populate preview from restored selection whenever documents load
            if detailDocument == nil,
               let firstSelectedId = browserSelection.first,
               let doc = newDocs.first(where: { $0.id == firstSelectedId }) {
                detailDocument = doc
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
            // Left side: Layout picker, View mode picker, Plus button
            // Conditional based on sidebar mode
            if showNavigationToolbar {
                ToolbarItemGroup(placement: .navigation) {
                    // Layout mode picker (None/Standard/Widescreen) - only for modes with preview
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
                        let hasSelection = !browserSelection.isEmpty || detailDocument != nil
                        let collectionFiles = documentStore.currentDocuments.filter { $0.docType == .file }
                        let hasCollection = !collectionFiles.isEmpty
                        let sortedWorkflows = workflowStore.workflows.sorted {
                            $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
                        }
                        Menu {
                            if workflowStore.workflows.isEmpty {
                                Text("No workflows available")
                            } else {
                                if hasSelection {
                                    Section("On Selection") {
                                        ForEach(sortedWorkflows, id: \.id) { workflow in
                                            Button(workflow.name) {
                                                runWorkflowOnSelection(workflowId: workflow.id)
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
                                if !hasSelection && !hasCollection {
                                    Text("Select a document or open a collection")
                                        .foregroundStyle(.secondary)
                                }
                            }
                        } label: {
                            Label("Run Workflow", systemImage: "play.square.stack")
                        }
                        .help("Run Workflow on Selection or Collection")
                        .disabled(workflowStore.workflows.isEmpty || (!hasSelection && !hasCollection))
                    }
                }
            }

            // Far right: Inspector toggle (after search widget, explicit trailing position)
            // Only show for content modes that use inspector
            // Search field only shown in search mode — avoids confusion in other modes
            if featureManager.isSearchEnabled && sidebarMode == .search {
                ToolbarItem(placement: .principal) {
                    HStack {
                        Image(systemName: "magnifyingglass")
                            .foregroundStyle(.secondary)
                        TextField("Search", text: $toolbarSearchText)
                            .textFieldStyle(.plain)
                            .onSubmit {
                                runToolbarSearch(toolbarSearchText)
                            }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .frame(minWidth: 260, idealWidth: 340, maxWidth: 460)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(Color(nsColor: .controlBackgroundColor))
                    )
                }
            }

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

            // Inspector toggle at the trailing edge of the toolbar (standard macOS placement).
            if showInspectorToggle {
                ToolbarItem(placement: .automatic) {
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            showInspectorSidebar.toggle()
                        }
                    } label: {
                        Image(systemName: "info.circle")
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
        }
        .onChange(of: selectedSidebarItemId) { _, newFolderId in
            // Restore per-folder view mode when switching folders
            if let saved = displayMode(for: newFolderId) {
                viewDisplayMode = normalizedViewDisplayMode(saved)
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
            // Sync preview with selection (covers both user clicks and restoration)
            if let firstId = newSelection.first,
               let doc = documentStore.currentDocuments.first(where: { $0.id == firstId }) {
                if detailDocument?.id != firstId {
                    detailDocument = doc
                }
            }
        }
        .onChange(of: detailDocument) { _, newDoc in
            // Keep documentStore.selectedDocument in sync so WorkflowEditor
            // toolbar button sees the current document at run time.
            documentStore.selectedDocument = newDoc
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

// MARK: - Preview
#Preview("Library Mode") {
    ContentView()
        .environmentObject(ViewSettings())
        .environmentObject(AppState())
        .frame(width: 1200, height: 700)
}
