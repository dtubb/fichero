import SwiftUI
import UniformTypeIdentifiers

/// Main content view with three-column navigation
/// Switches between Library, Search, and Workflow views based on sidebar selection
struct ContentView: View {
    // MARK: - Environment

    @EnvironmentObject var viewSettings: ViewSettings
    @EnvironmentObject var appState: AppState

    // MARK: - State

    @State private var viewMode: AppViewMode = .library(nil)
    @State private var selectedSidebarItemId: String?
    @State private var browserSelection: Set<String> = []
    @State private var detailDocument: Document?
    @State private var columnVisibility: NavigationSplitViewVisibility = .all

    // Document store - connects to Python backend
    @StateObject private var documentStore = DocumentStore()

    // Workflow store - manages workflow persistence
    @StateObject private var workflowStore = WorkflowStore()

    // Workflow state
    @State private var editingWorkflow: Workflow = Workflow(name: "New Workflow", description: "")

    // Chat state (shared between ChatView and ChatInspectorView)
    @State private var chatSelectedDocuments: Set<String> = []

    // Services - as StateObjects for EnvironmentObject injection
    @StateObject private var conversationService = ConversationService()
    @StateObject private var savedSearchService = SavedSearchService()
    @StateObject private var workflowService = WorkflowService()
    @StateObject private var performanceService = PerformanceService()
    @StateObject private var cacheModel = CacheModel()

    // Drag and drop state
    @State private var isDropTargeted = false
    @State private var isImporting = false
    @State private var importProgress: String?
    @State private var importError: String?

    // MARK: - Computed Properties

    // Cache for sidebar items - rebuilt only when source data changes
    @State private var cachedSidebarItems: [SidebarItem] = []

    /// Derive the selected SidebarItem from the ID (uses cached items)
    private var selectedSidebarItem: SidebarItem? {
        guard let id = selectedSidebarItemId else { return nil }
        return findItemById(id, in: cachedSidebarItems)
    }

    /// Rebuild the sidebar item cache from all sources
    private func rebuildSidebarCache() {
        let libraryItems = SidebarItemBuilder.buildLibraryHierarchy(from: documentStore.collections)
        let searchItems = SidebarItemBuilder.buildSearchHierarchy(from: savedSearchService.savedSearches)
        let chatItems = SidebarItemBuilder.buildChatHierarchy(from: conversationService.conversations)
        let workflowItems = SidebarItemBuilder.buildWorkflowHierarchy(from: workflowStore.workflows)

        cachedSidebarItems = libraryItems + searchItems + chatItems + workflowItems
    }

    /// Recursively find an item by ID
    private func findItemById(_ id: String, in items: [SidebarItem]) -> SidebarItem? {
        for item in items {
            if item.id == id {
                return item
            }
            if let children = item.children,
               let found = findItemById(id, in: children) {
                return found
            }
        }
        return nil
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
    private func handleDocumentChange(_ change: DocumentChange) {
        // Ensure we're on main thread for UI updates
        if !Thread.isMainThread {
            DispatchQueue.main.async {
                self.handleDocumentChangeOnMain(change)
            }
            return
        }
        handleDocumentChangeOnMain(change)
    }

    /// Handle document changes on main thread
    private func handleDocumentChangeOnMain(_ change: DocumentChange) {
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

    /// Navigation title based on current mode
    private var navigationTitle: String {
        switch viewMode {
        case .library(let doc):
            return doc?.name ?? "Library"
        case .search(let search):
            return search?.name ?? "Search"
        case .chat(let conversation):
            return conversation?.title ?? "Chat"
        case .workflow(let sidebarWorkflow):
            // If we have a specific workflow, show its name
            if let workflow = sidebarWorkflow {
                return workflow.name
            }
            // Otherwise check if we're editing one
            return editingWorkflow.name
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
            documentStore: documentStore,
            savedSearchService: savedSearchService,
            conversationService: conversationService,
            workflowStore: workflowStore,
            onCreateChatWithDocuments: { documentIds in
                chatSelectedDocuments = Set(documentIds)
            }
        )
        .environmentObject(savedSearchService)
        .environmentObject(conversationService)
        .environmentObject(workflowService)
        .environmentObject(ErrorService.shared)
        .environmentObject(performanceService)
        .environmentObject(cacheModel)
        .navigationSplitViewColumnWidth(min: 180, ideal: 220, max: 300)
    }

    @ViewBuilder
    private var centerContent: some View {
        contentView
            .navigationSplitViewColumnWidth(min: 300, ideal: 450, max: .infinity)
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
        .navigationTitle(navigationTitle)
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
                rebuildCache: rebuildSidebarCache,
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
            // Library browser with multiple view modes
            BrowserView(
                documents: selectedDocuments,
                selection: $browserSelection,
                detailDocument: $detailDocument,
                viewMode: viewSettings.browserViewMode
            )

        case .search(let savedSearch):
            // Search view with API integration
            SearchView(
                savedSearch: savedSearch,
                selection: $browserSelection,
                detailDocument: $detailDocument,
                onSearchSaved: { refreshSavedSearches() }
            )

        case .chat(let conversation):
            // RAG chat view for document conversations
            ChatView(
                conversation: conversation,
                selectedDocuments: $chatSelectedDocuments,
                onConversationUpdated: { refreshConversations() }
            )

         case .workflow(let workflow):
            // Workflow canvas + output log (inspector is in detail column)
            WorkflowView(
                workflow: workflow,
                editingWorkflow: $editingWorkflow
            )
        }
    }

    // MARK: - Detail View (Right Column)

    @ViewBuilder
    var detailView: some View {
        switch viewMode {
        case .library, .search:
            // Layout based on preview mode
            libraryDetailView

        case .chat:
            // Document scope inspector for chat
            ChatInspectorView(selectedDocuments: $chatSelectedDocuments)
                .navigationSplitViewColumnWidth(min: 200, ideal: 250, max: 300)

        case .workflow:
            // Workflow inspector with blocks to drag onto canvas
            WorkflowInspectorView(
                workflow: $editingWorkflow,
                onAddNode: { tool, position in
                    addNodeFromTool(tool, at: position)
                }
            )
            .navigationSplitViewColumnWidth(min: 240, ideal: 280, max: 350)
        }
    }

    @ViewBuilder
    var libraryDetailView: some View {
        switch viewSettings.previewMode {
        case .none:
            // No preview - just the editor
            EditorView(document: detailDocument)
                .toolbar {
                    libraryToolbar
                }

        case .standard:
            // Side by side (horizontal) - Editor + Inspector
            HStack(spacing: 0) {
                EditorView(document: detailDocument)

                if viewSettings.showInspector {
                    Divider()
                    InspectorView(document: inspectorDocument)
                }
            }
            .toolbar {
                libraryToolbar
            }

        case .widescreen:
            // Vertical split - Editor on top, Inspector below
            VSplitView {
                EditorView(document: detailDocument)
                    .frame(minHeight: 200)

                if viewSettings.showInspector {
                    InspectorView(document: inspectorDocument)
                        .frame(minHeight: 150)
                }
            }
            .toolbar {
                libraryToolbar
            }
        }
    }

    // MARK: - Toolbar (for Library/Search mode)

    @ToolbarContentBuilder
    var libraryToolbar: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            // View mode picker
            Picker("View", selection: $viewSettings.browserViewMode) {
                Image(systemName: "square.grid.2x2")
                    .tag(BrowserViewMode.icons)
                Image(systemName: "list.bullet")
                    .tag(BrowserViewMode.list)
                Image(systemName: "tablecells")
                    .tag(BrowserViewMode.table)
                Image(systemName: "rectangle.3.group")
                    .tag(BrowserViewMode.map)
            }
            .pickerStyle(.segmented)
            .frame(width: 140)

            Divider()

            // Inspector toggle on the right
            Button(action: { viewSettings.showInspector.toggle() }) {
                Image(systemName: "sidebar.right")
            }
            .help(viewSettings.showInspector ? "Hide Inspector" : "Show Inspector")
        }
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

    /// Add a node from a tool definition to the current workflow
    func addNodeFromTool(_ tool: ToolInfo, at position: CGPoint) {
        let newNode = WorkflowNode(from: tool, positionX: position.x, positionY: position.y)
        editingWorkflow.nodes.append(newNode)
        NSLog("[ContentView] Added node '\(tool.displayName)' at (\(position.x), \(position.y))")
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
                NSLog("[ContentView] Failed to refresh conversations: %@", error.localizedDescription)
            }
        }
    }

    // MARK: - Saved Searches

    func refreshSavedSearches() {
        Task {
            do {
                try await savedSearchService.loadSavedSearches()
            } catch {
                NSLog("[ContentView] Failed to refresh saved searches: %@", error.localizedDescription)
            }
        }
    }

    // MARK: - File Import

    /// Handle files dropped from Finder
    func handleFileDrop(urls: [URL]) {
        NSLog("[ContentView] Files dropped: \(urls.map { $0.lastPathComponent })")

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
                        NSLog("[ContentView] Skipping non-file URL: \(url)")
                        continue
                    }

                    // Update progress
                    await MainActor.run {
                        importProgress = "Importing \(url.lastPathComponent)..."
                    }

                    // Import the file
                    NSLog("[ContentView] Importing file: \(url.path)")
                    _ = try await documentStore.importFile(at: url, parentId: targetParentId)
                    successCount += 1

                } catch {
                    NSLog("[ContentView] Failed to import \(url.lastPathComponent): \(error)")
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
                        NSLog("[ContentView] Successfully imported \(successCount) file(s)")
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
    let rebuildCache: () -> Void

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
                rebuildCache()
            }
            .onChange(of: documentStore.collections) { _, _ in rebuildCache() }
            .onChange(of: savedSearchService.savedSearches) { _, _ in rebuildCache() }
            .onChange(of: conversationService.conversations) { _, _ in rebuildCache() }
            .onChange(of: workflowStore.workflows) { _, _ in rebuildCache() }
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

    let rebuildCache: () -> Void
    let handleDocumentChange: (DocumentChange) -> Void
    let handleFileDrop: ([URL]) -> Void

    func body(content: Content) -> some View {
        content
            .modifier(DataLoadingModifiers(
                documentStore: documentStore,
                workflowStore: workflowStore,
                conversationService: conversationService,
                savedSearchService: savedSearchService,
                rebuildCache: rebuildCache
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
                    NSLog("[ContentView] Failed to load workflow: %@", error.localizedDescription)
                    editingWorkflow = Workflow(id: item.id, name: item.name, description: item.description ?? "")
                }
            }
        }

        // Load children from backend when library item selected
        if case .library(let doc) = newMode, let document = doc {
            Task {
                await documentStore.selectCollection(document)
            }
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
