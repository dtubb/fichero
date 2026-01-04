import SwiftUI
import UniformTypeIdentifiers
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ContentView")

/// Main content view with three-column navigation
/// Switches between Library, Search, and Workflow views based on sidebar selection
struct ContentView: View {
    // MARK: - Environment

    @EnvironmentObject var viewSettings: ViewSettings
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var apiClient: APIClient
    @EnvironmentObject var documentStore: DocumentStore
    @EnvironmentObject var conversationService: ConversationService
    @EnvironmentObject var importService: ImportService
    @EnvironmentObject var windowState: WindowState
    @EnvironmentObject var workflowStore: WorkflowStore
    @EnvironmentObject var savedSearchService: SavedSearchService

    // MARK: - State

    @State private var viewMode: AppViewMode = .library(nil)
    @State private var selectedSidebarItemId: String?
    @State private var browserSelection: Set<String> = []
    @State private var detailDocument: Document?
    @State private var columnVisibility: NavigationSplitViewVisibility = .all

    // Workflow state
    @State private var editingWorkflow: Workflow = Workflow(name: "New Workflow", description: "")

    // Chat state (shared between ChatView and ChatInspectorView)
    @State private var chatSelectedDocuments: Set<String> = []

    // Main toolbar state (per-window persistence)
    @SceneStorage("viewDisplayMode") private var viewDisplayMode: ViewDisplayMode = .icon
    @SceneStorage("currentLayoutMode") private var currentLayoutMode: LayoutMode = .standard

    // Column visibility persistence
    @SceneStorage("sidebarWidth") private var sidebarWidth: Double = 220
    @SceneStorage("contentWidth") private var contentWidth: Double = 600
    @SceneStorage("inspectorWidth") private var inspectorWidth: Double = 250
    @SceneStorage("showSidebar") private var showSidebar: Bool = true
    @SceneStorage("showInspectorSidebar") private var showInspectorSidebar: Bool = true

    // Map view persistence (latitude, longitude, zoom)
    @SceneStorage("mapLatitude") private var mapLatitude: Double = 0.0
    @SceneStorage("mapLongitude") private var mapLongitude: Double = 0.0
    @SceneStorage("mapZoom") private var mapZoom: Double = 1.0

    @StateObject private var itemRegistry = ItemTypeRegistry()

    // Temp services (TODO: move to DocumentTabView)
    @StateObject private var performanceService = PerformanceService()

    // Error service (using singleton pattern)
    @ObservedObject private var errorService = ErrorService.shared

    // Drag and drop state
    @State private var isDropTargeted = false
    @State private var isImporting = false
    @State private var importProgress: String?
    @State private var importError: String?

    // MARK: - Computed Properties

    /// Toolbar title showing library name and current view
    private var toolbarTitle: String {
        let libraryManager = LibraryManager.shared
        let libraryName: String

        if let currentId = libraryManager.currentLibraryId,
           let library = libraryManager.openLibraries.first(where: { $0.id == currentId }) {
            libraryName = library.displayName
        } else {
            libraryName = "Fichero"
        }

        let viewName: String
        switch viewMode {
        case .library(let document):
            // Show actual document name, or "Library" if browsing all documents
            viewName = document?.name ?? "Library"
        case .search(let savedSearch):
            viewName = savedSearch?.name ?? "Search"
        case .chat(let conversation):
            // Show actual conversation title, or "Chat" if no conversation selected
            viewName = conversation?.title ?? "Chat"
        case .workflow(let workflow):
            viewName = workflow?.name ?? "Workflow"
        }

        return "\(libraryName) > \(viewName)"
    }

    /// Documents for the browser based on current library selection
    private var selectedDocuments: [Document] {
        return documentStore.currentDocuments
    }

    /// Document to show in inspector
    private var inspectorDocument: Document? {
        if let firstId = browserSelection.first {
            return documentStore.currentDocuments.first { $0.id == firstId }
        }
        return detailDocument
    }

    /// Handle document change events
    @MainActor
    private func handleDocumentChange(_ change: DocumentChange) {
        switch change {
        case .collectionsUpdated:
            // SwiftUI automatically updates when @Published collections change
            break

        case .collectionSelected(let collection):
            // Update selection if needed
            selectedSidebarItemId = collection.id

        case .documentsUpdated:
            // SwiftUI automatically updates when @Published currentDocuments change
            break

        case .documentDeleted(let document):
            // Remove deleted document from selection
            browserSelection.remove(document.id)
            if detailDocument?.id == document.id {
                detailDocument = nil
            }

        case .documentCreated:
            // SwiftUI automatically updates when @Published collections change
            break
        }
    }

    /// Whether we're in workflow mode
    private var isWorkflowMode: Bool {
        if case .workflow = viewMode { return true }
        return false
    }

    // MARK: - View Helpers

    @ViewBuilder
    private var sidebarContent: some View {
        SidebarView(
            viewMode: $viewMode,
            selectedItemId: $selectedSidebarItemId,
            libraryManager: LibraryManager.shared,
            onCreateChatWithDocuments: { documentIds in
                chatSelectedDocuments = Set(documentIds)
            },
            itemRegistry: itemRegistry
        )
        .environmentObject(savedSearchService)
        .environmentObject(conversationService)
        .environmentObject(ErrorService.shared)
        .environmentObject(performanceService)
        .navigationSplitViewColumnWidth(min: 180, ideal: sidebarWidth, max: 300)
    }

    @ViewBuilder
    private var centerContent: some View {
        switch currentLayoutMode {
        case .none:
            // None: Just content, no preview
            contentView
                .navigationSplitViewColumnWidth(min: 350, ideal: 600, max: .infinity)

        case .standard:
            // Standard: Content stacked above preview (vertical split)
            // Default: 20% content, 80% preview - emphasize document viewing
            VSplitView {
                contentView
                    .frame(minHeight: 150, idealHeight: 180)

                previewView
                    .frame(minHeight: 400, idealHeight: 720)
            }
            .navigationSplitViewColumnWidth(min: 350, ideal: 700, max: .infinity)

        case .widescreen:
            // Widescreen: Content and preview side-by-side (horizontal split)
            // Default: 20% content, 80% preview - emphasize document viewing
            HSplitView {
                contentView
                    .frame(minWidth: 200, idealWidth: 200)

                previewView
                    .frame(minWidth: 400, idealWidth: 800)
            }
            .navigationSplitViewColumnWidth(min: 600, ideal: 1000, max: .infinity)
        }
    }

    /// Preview/editor view for selected item
    @ViewBuilder
    private var previewView: some View {
        switch viewMode {
        case .library, .search:
            EditorView(document: detailDocument)

        case .chat:
            // Chat doesn't have a traditional preview
            EmptyView()

        case .workflow:
            // Workflow doesn't have a traditional preview
            EmptyView()
        }
    }

    /// Inspector/info sidebar view (right column - fixed width)
    @ViewBuilder
    private var inspectorView: some View {
        switch viewMode {
        case .library, .search:
            DocumentInspector(document: inspectorDocument)
                .navigationSplitViewColumnWidth(250)
                .frame(width: 250)

        case .chat:
            ChatInspector(selectedDocuments: $chatSelectedDocuments)
                .navigationSplitViewColumnWidth(250)
                .frame(width: 250)

        case .workflow:
            WorkflowInspector(
                workflow: $editingWorkflow,
                onAddNode: { tool, position in
                    addNodeFromTool(tool, at: position)
                }
            )
            .navigationSplitViewColumnWidth(280)
            .frame(width: 280)
        }
    }

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

                    Divider()
                        .frame(width: 200)

                    VStack(alignment: .leading, spacing: 8) {
                        Text("To start the API, run:")
                            .font(.headline)

                        Text("cd /Users/dtubb/code/fichero_main/fichero")
                            .font(.system(.body, design: .monospaced))
                            .padding(8)
                            .background(Color(nsColor: .controlBackgroundColor))
                            .cornerRadius(4)

                        Text("PYTHONPATH=src .venv/bin/uvicorn fichero.api.main:app --port 8765")
                            .font(.system(.body, design: .monospaced))
                            .padding(8)
                            .background(Color(nsColor: .controlBackgroundColor))
                            .cornerRadius(4)
                    }

                    HStack(spacing: 16) {
                        Button("Retry") {
                            Task {
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
            }
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
        NavigationSplitView(
            columnVisibility: $columnVisibility,
            sidebar: { sidebarContent },
            content: { centerContent },
            detail: { detailView }
        )
        .navigationSplitViewStyle(.prominentDetail)
        .navigationTitle(toolbarTitle)  // Show title in window tab and toolbar
        .navigationSubtitle("")  // No subtitle (path suppressed)
        .toolbar(removing: .sidebarToggle)
        .onAppear {
            // Initialize column visibility based on persisted inspector state
            updateColumnVisibility()
        }
        .onChange(of: showInspectorSidebar) { _, _ in
            // Update column visibility when inspector toggle changes
            updateColumnVisibility()
        }
        .toolbar {
            // Left side: Layout picker, View mode picker, Plus button
            ToolbarItemGroup(placement: .navigation) {
                // Layout mode picker (None/Standard/Widescreen) with icons
                Picker("Layout", selection: $currentLayoutMode) {
                    ForEach(LayoutMode.allCases) { mode in
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
                        switch newMode {
                        case .none:
                            viewSettings.previewMode = .none
                        case .standard:
                            viewSettings.previewMode = .standard
                        case .widescreen:
                            viewSettings.previewMode = .widescreen
                        }
                    }
                }

                // View mode picker (Icon/List/Table/Map)
                Picker("View", selection: $viewDisplayMode) {
                    ForEach(ViewDisplayMode.allCases) { mode in
                        Label(mode.rawValue, systemImage: mode.icon)
                            .labelStyle(.iconOnly)
                            .tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .help("View as: \(viewDisplayMode.rawValue)")
                .onChange(of: viewDisplayMode) { _, newMode in
                    // Sync toolbar with View menu libraryLayout
                    switch newMode {
                    case .icon:
                        viewSettings.libraryLayout = .icons
                    case .list:
                        viewSettings.libraryLayout = .list
                    case .table:
                        viewSettings.libraryLayout = .table
                    case .map:
                        viewSettings.libraryLayout = .map
                    }
                }

                // Add menu (Plus button)
                AddItemMenu(registry: itemRegistry, style: .button)
                    .help("Add new item (⌘N)")
            }

            // Far right: Inspector toggle (after search widget, explicit trailing position)
            ToolbarItem(placement: .primaryAction) {
                Button(action: {
                    withAnimation {
                        showInspectorSidebar.toggle()
                    }
                }) {
                    Image(systemName: "sidebar.right")
                }
                .help(showInspectorSidebar ? "Hide Inspector (⌘⌥I)" : "Show Inspector (⌘⌥I)")
            }
        }
        .onChange(of: viewSettings.previewMode) { _, newPreviewMode in
            // Sync View menu changes back to toolbar layout picker
            let newLayoutMode: LayoutMode
            switch newPreviewMode {
            case .none:
                newLayoutMode = .none
            case .standard:
                newLayoutMode = .standard
            case .widescreen:
                newLayoutMode = .widescreen
            }

            if currentLayoutMode != newLayoutMode {
                withAnimation {
                    currentLayoutMode = newLayoutMode
                }
            }
        }
        .onChange(of: viewSettings.libraryLayout) { _, newLibraryLayout in
            // Sync View menu changes back to toolbar view mode picker
            let newDisplayMode: ViewDisplayMode
            switch newLibraryLayout {
            case .icons:
                newDisplayMode = .icon
            case .list:
                newDisplayMode = .list
            case .table:
                newDisplayMode = .table
            case .map:
                newDisplayMode = .map
            }

            if viewDisplayMode != newDisplayMode {
                viewDisplayMode = newDisplayMode
            }
        }
        .modifier(
            MainContentModifiers(
                documentStore: documentStore,
                workflowStore: workflowStore,
                conversationService: conversationService,
                savedSearchService: savedSearchService,
                appState: appState,
                viewSettings: viewSettings,
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

extension ContentView {
    // MARK: - Content View (Middle Column)

    @ViewBuilder
    var contentView: some View {
        switch viewMode {
        case .library:
            // Library browser with universal view modes
            LibraryView(
                documents: selectedDocuments,
                selection: $browserSelection,
                detailDocument: $detailDocument,
                viewMode: $viewSettings.libraryLayout,
                displayMode: viewDisplayMode
            )

        case .search(let savedSearch):
            // Search view with universal view modes
            SearchView(
                savedSearch: savedSearch,
                selection: $browserSelection,
                detailDocument: $detailDocument,
                onSearchSaved: { refreshSavedSearches() },
                displayMode: viewDisplayMode
            )

        case .chat(let conversation):
            // RAG chat view with universal view modes
            ChatView(
                conversation: conversation,
                selectedDocuments: $chatSelectedDocuments,
                onConversationUpdated: { refreshConversations() },
                displayMode: viewDisplayMode
            )

         case .workflow(let workflow):
            // Workflow canvas with universal view modes
            WorkflowEditor(
                workflow: workflow,
                editingWorkflow: $editingWorkflow,
                displayMode: viewDisplayMode
            )
        }
    }

    // MARK: - Detail View (Right Column)

    @ViewBuilder
    var detailView: some View {
        // Detail column ALWAYS shows just the inspector, regardless of layout mode
        // The inspector visibility is controlled by the inspector toggle button
        inspectorView
    }

    // MARK: - Breadcrumb

    @ViewBuilder
    func breadcrumbView(for doc: Document) -> some View {
        // TODO: Load ancestors from API via documentStore
        HStack(spacing: 4) {
            Text(doc.name)
                .fontWeight(.medium)
        }
    }

    // MARK: - Actions

    func toggleSidebar() {
        withAnimation {
            if columnVisibility == .all {
                columnVisibility = .doubleColumn
            } else {
                columnVisibility = .all
            }
        }
    }

    /// Update column visibility based on inspector sidebar state
    private func updateColumnVisibility() {
        withAnimation {
            if showInspectorSidebar {
                // Show all three columns: sidebar, content, and inspector
                columnVisibility = .all
            } else {
                // Show only sidebar and content, hide inspector
                columnVisibility = .doubleColumn
            }
        }
    }

    /// Add a node from a tool definition to the current workflow
    func addNodeFromTool(_ tool: ToolInfo, at position: CGPoint) {
        let newNode = WorkflowNode(from: tool, positionX: position.x, positionY: position.y)
        editingWorkflow.nodes.append(newNode)
        logger.info("Added node '\(tool.displayName)' at (\(position.x), \(position.y))")
    }

    // MARK: - Navigation

    func navigateToDocument(_ doc: Document) {
        viewMode = .library(doc)
        selectedSidebarItemId = doc.id
    }

    // MARK: - Conversations

    func refreshConversations() {
        Task {
            do {
                try await conversationService.loadConversations()
            } catch {
                logger.error("Failed to refresh conversations: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Saved Searches

    func refreshSavedSearches() {
        Task {
            do {
                try await savedSearchService.loadSavedSearches()
            } catch {
                logger.error("Failed to refresh saved searches: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - File Import

    /// Handle files dropped from Finder
    func handleFileDrop(urls: [URL]) {
        logger.info("Files dropped: \(urls.map { $0.lastPathComponent })")

        // Determine target parent ID from current selection
        var targetParentId: String?
        if case .library(let doc) = viewMode {
            targetParentId = doc?.id
        }

        Task {
            isImporting = true
            importError = nil

            var successCount = 0
            var failedFiles: [String] = []

            for url in urls {
                do {
                    // Check if it's a file URL
                    guard url.isFileURL else {
                        logger.warning("Skipping non-file URL: \(url)")
                        continue
                    }

                    // Update progress
                    await MainActor.run {
                        importProgress = "Importing \(url.lastPathComponent)..."
                    }

                    // Import the file
                    logger.info("Importing file: \(url.path)")
                    _ = try await documentStore.importFile(at: url, parentId: targetParentId)
                    successCount += 1

                } catch {
                    logger.error("Failed to import \(url.lastPathComponent): \(String(describing: error))")
                    failedFiles.append(url.lastPathComponent)
                }
            }

            // Update UI
            await MainActor.run {
                isImporting = false
                importProgress = nil

                if !failedFiles.isEmpty {
                    let fileList = failedFiles.joined(separator: ", ")
                    importError = "Failed to import \(failedFiles.count) file(s): \(fileList)"
                }

                // Refresh collections to show newly imported items
                if successCount > 0 {
                    Task {
                        await documentStore.loadCollections()
                        logger.info("Successfully imported \(successCount) file(s)")
                    }
                }
            }
        }
    }
}

// MARK: - View Modifiers

/// Data loading modifiers (initial task + cache rebuilding)
struct DataLoadingModifiers: ViewModifier {
    let documentStore: DocumentStore
    let workflowStore: WorkflowStore
    let conversationService: ConversationService
    let savedSearchService: SavedSearchService

    func body(content: Content) -> some View {
        content
            .task {
                await withTaskGroup(of: Void.self) { group in
                    group.addTask {
                        guard !Task.isCancelled else { return }
                        await documentStore.loadCollections()
                    }
                    group.addTask {
                        guard !Task.isCancelled else { return }
                        await workflowStore.loadWorkflows()
                    }
                    group.addTask {
                        guard !Task.isCancelled else { return }
                        try? await conversationService.loadConversations()
                    }
                    group.addTask {
                        guard !Task.isCancelled else { return }
                        try? await savedSearchService.loadSavedSearches()
                    }
                }
            }
    }
}

/// Change handler modifiers (view mode, sidebar mode, browser selection)
struct ChangeHandlerModifiers: ViewModifier {
    let documentStore: DocumentStore
    @Binding var viewMode: AppViewMode
    let viewSettings: ViewSettings
    @Binding var browserSelection: Set<String>
    @Binding var detailDocument: Document?

    let handleViewModeChange: (AppViewMode) -> Void
    let handleSidebarModeChange: (SidebarMode) -> Void
    let handleBrowserSelectionChange: (Set<String>) -> Void
    let handleDocumentChange: (DocumentChange) -> Void

    func body(content: Content) -> some View {
        content
            .onChange(of: viewMode) { _, newMode in
                handleViewModeChange(newMode)
            }
            .onChange(of: viewSettings.sidebarMode) { _, newMode in
                handleSidebarModeChange(newMode)
            }
            .onChange(of: browserSelection) { _, newSelection in
                handleBrowserSelectionChange(newSelection)
            }
            .onReceive(
                documentStore.documentChangePublisher
                    .replaceError(with: DocumentChange.collectionsUpdated([]))
            ) { change in
                handleDocumentChange(change)
            }
    }
}

/// Sheet modifiers (provider sheets)
struct SheetModifiers: ViewModifier {
    let appState: AppState

    func body(content: Content) -> some View {
        content
            .sheet(isPresented: Binding(
                get: { appState.showAddProvider },
                set: { appState.showAddProvider = $0 }
            )) {
                AddProviderSheet(
                    onAdd: {
                        await appState.loadProviders()
                        appState.isFirstLaunchProviderSetup = false
                    },
                    isFirstLaunch: appState.isFirstLaunchProviderSetup
                )
            }
            .sheet(isPresented: Binding(
                get: { appState.showProvidersSettings },
                set: { appState.showProvidersSettings = $0 }
            )) {
                ProvidersSettingsSheet()
                    .environmentObject(appState)
            }
    }
}

/// Drop target and import overlays
struct DropTargetModifiers: ViewModifier {
    @Binding var isDropTargeted: Bool
    @Binding var isImporting: Bool
    @Binding var importProgress: String?
    @Binding var importError: String?
    let handleFileDrop: ([URL]) -> Void

    func body(content: Content) -> some View {
        content
            .dropDestination(for: URL.self) { urls, _ in
                handleFileDrop(urls)
                return true
            } isTargeted: { isTargeted in
                self.isDropTargeted = isTargeted
            }
            .overlay {
                if isDropTargeted {
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.accentColor, lineWidth: 2)
                        .padding(4)
                        .allowsHitTesting(false)
                }
            }
            .overlay {
                if isImporting {
                    ZStack {
                        Color.black.opacity(0.3)
                        VStack(spacing: 12) {
                            ProgressView()
                                .scaleEffect(1.2)
                            if let progress = importProgress {
                                Text(progress)
                                    .foregroundColor(.white)
                            }
                        }
                        .padding(20)
                        .background(Color(nsColor: .controlBackgroundColor))
                        .cornerRadius(8)
                    }
                    .allowsHitTesting(false)
                }
            }
            .alert("Import Error", isPresented: .constant(importError != nil)) {
                Button("OK") {
                    importError = nil
                }
            } message: {
                if let error = importError {
                    Text(error)
                }
            }
    }
}

/// Splits mainContentView modifiers into a separate struct to avoid compiler timeout
struct MainContentModifiers: ViewModifier {
    let documentStore: DocumentStore
    let workflowStore: WorkflowStore
    let conversationService: ConversationService
    let savedSearchService: SavedSearchService
    let appState: AppState
    let viewSettings: ViewSettings

    @Binding var viewMode: AppViewMode
    @Binding var selectedSidebarItemId: String?
    @Binding var browserSelection: Set<String>
    @Binding var detailDocument: Document?
    @Binding var columnVisibility: NavigationSplitViewVisibility
    @Binding var editingWorkflow: Workflow
    @Binding var isDropTargeted: Bool
    @Binding var isImporting: Bool
    @Binding var importProgress: String?
    @Binding var importError: String?

    let handleDocumentChange: (DocumentChange) -> Void
    let handleFileDrop: ([URL]) -> Void

    func body(content: Content) -> some View {
        content
            .modifier(DataLoadingModifiers(
                documentStore: documentStore,
                workflowStore: workflowStore,
                conversationService: conversationService,
                savedSearchService: savedSearchService
            ))
            .modifier(ChangeHandlerModifiers(
                documentStore: documentStore,
                viewMode: $viewMode,
                viewSettings: viewSettings,
                browserSelection: $browserSelection,
                detailDocument: $detailDocument,
                handleViewModeChange: handleViewModeChange,
                handleSidebarModeChange: handleSidebarModeChange,
                handleBrowserSelectionChange: handleBrowserSelectionChange,
                handleDocumentChange: handleDocumentChange
            ))
            .modifier(SheetModifiers(appState: appState))
            .modifier(DropTargetModifiers(
                isDropTargeted: $isDropTargeted,
                isImporting: $isImporting,
                importProgress: $importProgress,
                importError: $importError,
                handleFileDrop: handleFileDrop
            ))
    }

    private func handleViewModeChange(_ newMode: AppViewMode) {
        logger.info("handleViewModeChange called with mode: \(String(describing: newMode))")

        // Load workflow from API when workflow mode changes
        if case .workflow(let workflowItem) = newMode, let item = workflowItem {
            Task {
                do {
                    let fullWorkflow = try await workflowStore.getWorkflow(item.id)
                    editingWorkflow = Workflow(
                        id: fullWorkflow.id,
                        name: fullWorkflow.name,
                        description: fullWorkflow.description
                    )
                } catch {
                    logger.error("Failed to load workflow: \(error.localizedDescription)")
                    editingWorkflow = Workflow(id: item.id, name: item.name, description: item.description ?? "")
                }
            }
        }

        // Load children from backend when library folder selected
        if case .library(let doc) = newMode, let document = doc {
            // Only load children for folders, not files
            if document.docType == .folder {
                logger.info("Loading children for folder: \(document.name) (id: \(document.id))")
                Task {
                    await documentStore.selectCollection(document)
                    logger.info("selectCollection completed. currentDocuments count: \(documentStore.currentDocuments.count)")
                }
            } else {
                logger.info("Showing single file in gallery: \(document.name)")
                // Show the selected file as a single item in the gallery
                documentStore.currentDocuments = [document]
            }
        } else if case .library(nil) = newMode {
            logger.info("Library mode with no document selected - showing all documents")
        }

        // Always show all 3 columns
        columnVisibility = .all
    }

    private func handleSidebarModeChange(_ newMode: SidebarMode) {
        switch newMode {
        case .navigate:
            if case .library = viewMode { return }
            viewMode = .library(nil)
        case .search:
            viewMode = .search(nil)
        case .chat:
            viewMode = .chat(nil)
        case .workflows:
            viewMode = .workflow(nil)
        case .activity:
            break
        }
    }

    private func handleBrowserSelectionChange(_ newSelection: Set<String>) {
        if let firstId = newSelection.first,
           let doc = documentStore.currentDocuments.first(where: { $0.id == firstId }) {
            detailDocument = doc
        } else if newSelection.isEmpty {
            detailDocument = nil
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
