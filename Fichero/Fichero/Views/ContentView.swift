import SwiftUI
import UniformTypeIdentifiers
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ContentView")

/// Main content view with three-column navigation
/// Switches between Library, Search, and Workflow views based on sidebar selection
// swiftlint:disable:next type_body_length
struct ContentView: View {
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
    @SceneStorage("sidebarMode") private var sidebarMode: SidebarMode = .library

    // Column visibility persistence
    @SceneStorage("sidebarWidth") private var sidebarWidth: Double = 280
    @SceneStorage("contentWidth") private var contentWidth: Double = 600
    @SceneStorage("inspectorWidth") private var inspectorWidth: Double = 250
    @SceneStorage("showSidebar") private var showSidebar: Bool = true
    @SceneStorage("showInspectorSidebar") private var showInspectorSidebar: Bool = true

    // Map view persistence (latitude, longitude, zoom)
    @SceneStorage("mapLatitude") private var mapLatitude: Double = 0.0
    @SceneStorage("mapLongitude") private var mapLongitude: Double = 0.0
    @SceneStorage("mapZoom") private var mapZoom: Double = 1.0

    @StateObject private var itemRegistry = ItemTypeRegistry()

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
        case .comparison(let comparison):
            // Show comparison prompt snippet, or "Comparison" if none selected
            if let comp = comparison {
                let truncated = comp.prompt.count > 30 ? String(comp.prompt.prefix(30)) + "..." : comp.prompt
                viewName = truncated
            } else {
                viewName = "Comparison"
            }
        case .workflow(let workflow):
            viewName = workflow?.name ?? "Workflow"
        case .chain(let chain):
            viewName = chain?.name ?? "Chain"
        case .batches:
            viewName = "Batches"
        case .batch(let batch):
            viewName = batch.map { "Batch \(String($0.batchId.prefix(8)))" } ?? "Batch"
        case .automation:
            viewName = "Automation"
        case .schedule(let schedule):
            viewName = schedule?.name ?? "Schedule"
        case .trigger(let trigger):
            viewName = trigger?.name ?? "Trigger"
        case .activity:
            viewName = "Activity"
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

    /// Whether to show the navigation toolbar (layout/view pickers, add button)
    /// Only show for content modes (library, search, chat, workflows)
    private var showNavigationToolbar: Bool {
        switch viewMode {
        case .library, .search, .chat, .comparison, .workflow, .chain:
            return true
        case .batches, .batch, .automation, .schedule, .trigger, .activity:
            return false
        }
    }

    /// Whether to show the inspector toggle button
    /// Only show for modes that have an inspector view
    private var showInspectorToggle: Bool {
        switch viewMode {
        case .library, .search, .chat, .comparison, .workflow, .chain:
            return true
        case .batches, .batch, .automation, .schedule, .trigger, .activity:
            return false
        }
    }

    /// Whether to show the view mode picker (icon/list/table/map)
    /// Only makes sense for Library and Search modes
    private var showViewModePicker: Bool {
        switch sidebarMode {
        case .library, .search:
            return true
        case .chat, .workflows, .automation, .batches, .activity:
            return false
        }
    }

    /// Whether to show the layout mode picker (none/standard/widescreen)
    /// Show for modes that have preview/inspector layouts
    private var showLayoutPicker: Bool {
        switch sidebarMode {
        case .library, .search, .chat, .workflows:
            return true
        case .automation, .batches, .activity:
            return false
        }
    }

    // MARK: - View Helpers

    @ViewBuilder
    private var sidebarContent: some View {
        SidebarView(
            sidebarMode: $sidebarMode,
            viewMode: $viewMode,
            selectedItemId: $selectedSidebarItemId,
            libraryManager: LibraryManager.shared,
            itemRegistry: itemRegistry,
            apiClient: apiClient,
            onCreateChatWithDocuments: { documentIds in
                chatSelectedDocuments = Set(documentIds)
            }
        )
        .environmentObject(savedSearchService)
        .environmentObject(conversationService)
        .environmentObject(ErrorService.shared)
        .environmentObject(performanceService)
        .navigationSplitViewColumnWidth(min: 250, ideal: sidebarWidth, max: 350)
        .focusedSceneValue(\.sidebarMode, $sidebarMode)
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

        case .chat, .comparison:
            // Chat and comparison don't have a traditional preview
            EmptyView()

        case .workflow, .chain:
            // Workflow and chain don't have a traditional preview
            EmptyView()

        case .batches, .batch, .automation, .schedule, .trigger, .activity:
            // Activity/automation modes don't have a traditional preview
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

        case .chat, .comparison:
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

        case .chain:
            // Chain editor - uses workflow inspector for now
            WorkflowInspector(
                workflow: $editingWorkflow,
                onAddNode: { tool, position in
                    addNodeFromTool(tool, at: position)
                }
            )
            .navigationSplitViewColumnWidth(280)
            .frame(width: 280)

        case .batches, .batch, .automation, .schedule, .trigger, .activity:
            // Activity/automation modes don't need an inspector
            EmptyView()
                .navigationSplitViewColumnWidth(0)
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
            // Conditional based on sidebar mode
            if showNavigationToolbar {
                ToolbarItemGroup(placement: .navigation) {
                    // Layout mode picker (None/Standard/Widescreen) - only for modes with preview
                    if showLayoutPicker {
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
                    }

                    // View mode picker (Icon/List/Table/Map) - only for Library/Search
                    if showViewModePicker {
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
                    }

                    // Add menu (Plus button)
                    AddItemMenu(registry: itemRegistry, style: .button)
                        .help("Add new item (⌘N)")
                }
            }

            // Far right: Inspector toggle (after search widget, explicit trailing position)
            // Only show for content modes that use inspector
            if showInspectorToggle {
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
        .onChange(of: viewMode) { oldMode, _ in
            // Auto-save workflow when navigating away from a workflow
            if case .workflow(let oldWorkflow) = oldMode, let workflow = oldWorkflow {
                // Capture the editing workflow content before it changes
                let workflowToSave = editingWorkflow
                Task { @MainActor in
                    await autoSaveWorkflow(workflowId: workflow.id, workflow: workflowToSave)
                }
            }
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

        case .comparison(let comparison):
            // Model comparison view
            if let comp = comparison {
                ComparisonDetailView(comparisonSummary: comp)
            } else {
                ModelComparisonView()
            }

         case .workflow(let workflow):
            if let selectedWorkflow = workflow {
                // Edit mode - show workflow canvas
                WorkflowEditor(
                    workflow: selectedWorkflow,
                    editingWorkflow: $editingWorkflow,
                    displayMode: viewDisplayMode
                )
            } else {
                // No workflow selected - show placeholder
                ContentUnavailableView(
                    "Workflows",
                    systemImage: "flowchart",
                    description: Text("Select a workflow or chain from the sidebar to edit")
                )
            }

        case .chain(let chain):
            if let selectedChain = chain {
                // Chain editor view
                ChainEditorView(chain: selectedChain)
            } else {
                ContentUnavailableView(
                    "Create Chain",
                    systemImage: "link.badge.plus",
                    description: Text("Chain creation view")
                )
            }

        case .batches:
            // Batch jobs - content shown in sidebar, main area shows details
            ContentUnavailableView(
                "Batches",
                systemImage: "square.stack.3d.up",
                description: Text("Select a batch in the sidebar to view details")
            )

        case .batch(let batch):
            // Batch detail view
            if let batch = batch {
                BatchDetailView(batch: batch, libraryManager: LibraryManager.shared)
            } else {
                ContentUnavailableView(
                    "Create Batch",
                    systemImage: "square.stack.3d.up.badge.plus",
                    description: Text("Batch creation view coming soon")
                )
            }

        case .automation:
            // Automation - content shown in sidebar, main area shows details
            ContentUnavailableView(
                "Automation",
                systemImage: "timer",
                description: Text("Select a schedule or trigger in the sidebar")
            )

        case .schedule(let schedule):
            // Schedule detail/creation view
            if let schedule = schedule {
                ScheduleDetailView(schedule: schedule)
            } else {
                // New schedule creation - use full-page editor
                ScheduleEditorView(existingSchedule: nil)
            }

        case .trigger(let trigger):
            // Trigger detail/creation view
            if let trigger = trigger {
                TriggerDetailView(trigger: trigger)
            } else {
                // New trigger creation - use full-page editor
                TriggerEditorView(existingTrigger: nil)
            }

        case .activity(let selectedRun):
            // Activity - all workflow runs shown in sidebar, main area shows run details
            if let run = selectedRun {
                ActivityDetailView(selectedRun: run)
            } else {
                ContentUnavailableView(
                    "Activity",
                    systemImage: "clock",
                    description: Text("Select a workflow run in the sidebar to view details")
                )
            }
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
        // Shows document name; full breadcrumb path could be added via documentStore.ancestors()
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

    /// Auto-save a workflow (called when switching views or app quits)
    /// - Parameters:
    ///   - workflowId: The ID of the workflow to save
    ///   - workflow: The workflow content to save
    @MainActor
    func autoSaveWorkflow(workflowId: String, workflow: Workflow) async {
        // Only save if there's content worth saving
        guard !workflow.nodes.isEmpty || !workflow.name.isEmpty else {
            logger.info("Auto-save skipped: empty workflow")
            return
        }

        logger.info("Auto-saving workflow: \(workflow.name) (id: \(workflowId))")
        // Debug: log node provider/model values at save time
        for node in workflow.nodes {
            print("[DEBUG SAVE] Node \(node.id): providerName=\(node.providerName ?? "nil"), modelName=\(node.modelName ?? "nil")")
        }
        do {
            let definition = workflow.toAPIFormat()
            // Always update since we have a workflow ID
            _ = try await workflowStore.updateWorkflow(definition)
            logger.info("Auto-save completed for workflow: \(workflowId)")
        } catch {
            logger.error("Auto-save failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Navigation

    func navigateToDocument(_ doc: Document) {
        viewMode = .library(doc)
        selectedSidebarItemId = doc.id
    }

    // MARK: - Conversations

    func refreshConversations() {
        Task { @MainActor in
            do {
                try await conversationService.loadConversations()
            } catch {
                logger.error("Failed to refresh conversations: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Saved Searches

    func refreshSavedSearches() {
        Task { @MainActor in
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

        Task { @MainActor in
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
                    Task { @MainActor in
                        await documentStore.loadCollections()
                        logger.info("Successfully imported \(successCount) file(s)")
                    }
                }
            }
        }
    }
}

// MARK: - Preview
// ViewModifier structs are in ContentViewModifiers.swift

#Preview("Library Mode") {
    ContentView()
        .environmentObject(ViewSettings())
        .environmentObject(AppState())
        .frame(width: 1200, height: 700)
}
