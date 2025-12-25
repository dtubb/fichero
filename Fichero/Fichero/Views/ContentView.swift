import SwiftUI

/// Main content view with three-column navigation
/// Switches between Library, Search, and Workflow views based on sidebar selection
struct ContentView: View {
    // MARK: - Environment

    @EnvironmentObject var viewSettings: ViewSettings
    @EnvironmentObject var appState: AppState

    // MARK: - State

    @State private var viewMode: AppViewMode = .library(nil)
    @State private var selectedSidebarItem: SidebarItem?
    @State private var browserSelection: Set<String> = []
    @State private var detailDocument: Document?
    @State private var columnVisibility: NavigationSplitViewVisibility = .all

    // Document store - connects to Python backend
    @StateObject private var documentStore = DocumentStore()
    
    // Force UI refresh counter
    @State private var refreshCounter = 0

    // Workflow store - manages workflow persistence
    @StateObject private var workflowStore = WorkflowStore()

    // Workflow state
    @State private var editingWorkflow: Workflow = Workflow(name: "New Workflow", description: "")

    // Chat state (shared between ChatView and ChatInspectorView)
    @State private var chatSelectedDocuments: Set<String> = []
    @State private var conversations: [Conversation] = []

    // Search state
    @State private var savedSearches: [SavedSearch] = []

    // Services - as StateObjects for EnvironmentObject injection
    @StateObject private var conversationService = ConversationService()
    @StateObject private var savedSearchService = SavedSearchService()
    @StateObject private var documentService = DocumentService()
    @StateObject private var workflowService = WorkflowService()

    // MARK: - Sidebar Data

    /// Build sidebar items from documentStore collections
    private var libraryItems: [SidebarItem] {
        return documentStore.collections.map { collection in
            SidebarItem.fromDocument(collection)
        }
    }

    private var searchItems: [SidebarItem] {
        savedSearches.map { SidebarItem.fromSearch($0) }
    }

    private var chatItems: [SidebarItem] {
        conversations.map { SidebarItem.fromConversation($0) }
    }

    private var workflowItems: [SidebarItem] {
        workflowStore.workflows.map { workflow in
            SidebarItem.fromWorkflow(workflow)
        }
    }

    // MARK: - Computed Properties

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
        case .collectionsUpdated(_):
            // Force UI refresh by updating state
            refreshCounter += 1
            
        case .collectionSelected(let collection):
            // Update selection if needed
            if let item = libraryItems.first(where: { $0.id == collection.id }) {
                selectedSidebarItem = item
            }

        case .documentsUpdated(_):
            // Force UI refresh for document updates
            refreshCounter += 1

        case .documentDeleted(let document):
            // Remove deleted document from selection
            browserSelection.remove(document.id)
            if detailDocument?.id == document.id {
                detailDocument = nil
            }
            // Force UI refresh
            refreshCounter += 1

        case .documentCreated(_):
            // Force UI refresh for new documents
            refreshCounter += 1
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
    private var mainContentView: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            // Sidebar with Library, Searches, Chat, Workflows sections
            SidebarView(
                viewMode: $viewMode,
                selectedItem: $selectedSidebarItem,
                libraryItems: libraryItems,
                searchItems: searchItems,
                chatItems: chatItems,
                workflowItems: workflowItems,
                onCreateChatWithDocuments: { documentIds in
                    // Add dropped documents to chat scope
                    chatSelectedDocuments = Set(documentIds)
                    ErrorService.shared.logger.info("[ContentView] Created chat with %d documents in scope", documentIds.count)
                }
            )
            .environmentObject(documentStore)
            .environmentObject(documentService)
            .environmentObject(savedSearchService)
            .environmentObject(conversationService)
            .environmentObject(workflowService)
            .environmentObject(ErrorService.shared)
            .navigationSplitViewColumnWidth(min: 180, ideal: 220, max: 300)
        } content: {
            // Content area - changes based on view mode
            contentView
                .navigationSplitViewColumnWidth(min: 300, ideal: 450, max: .infinity)
        } detail: {
            // Detail area - changes based on view mode
            detailView
        }
        .navigationTitle(navigationTitle)
        .task {
            // Load collections from backend
            await documentStore.loadCollections()

            // Load workflows from backend
            await workflowStore.loadWorkflows()

            // Load conversations from backend
            do {
                conversations = try await conversationService.getConversationsForSidebar()
            } catch {
                NSLog("[ContentView] Failed to load conversations: %@", error.localizedDescription)
            }

            // Load saved searches from backend
            do {
                savedSearches = try await savedSearchService.getSavedSearchesForSidebar()
            } catch {
                NSLog("[ContentView] Failed to load saved searches: %@", error.localizedDescription)
            }

            // Auto-select first library item
            if case .library(nil) = viewMode,
               let firstItem = libraryItems.first {
                selectedSidebarItem = firstItem
                if case .document(let doc) = firstItem.itemType {
                    viewMode = .library(doc)
                    await documentStore.selectCollection(doc)
                }
            }
        }
         .onChange(of: viewMode) { _, newMode in
             // Load workflow from API when workflow mode changes
             if case .workflow(let workflowItem) = newMode, let item = workflowItem {
                 // Load full workflow from API using item.id
                 Task {
                     do {
                         let fullWorkflow = try await workflowStore.getWorkflow(item.id)
                         // Convert from API response to local Workflow type
                         editingWorkflow = Workflow(
                             id: fullWorkflow.id,
                             name: fullWorkflow.name,
                             description: fullWorkflow.description
                         )
                     } catch {
                         NSLog("[ContentView] Failed to load workflow: %@", error.localizedDescription)
                         // Fallback to creating new workflow with matching name
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
        .onChange(of: viewSettings.sidebarMode) { _, newMode in
            // Respond to sidebar menu changes
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
                // TODO: Add activity view
                break
            }
        }
        .onChange(of: browserSelection) { _, newSelection in
            // Update preview when selection changes (single click)
            if let firstId = newSelection.first,
               let doc = documentStore.currentDocuments.first(where: { $0.id == firstId }) {
                detailDocument = doc
            } else if newSelection.isEmpty {
                detailDocument = nil
            }
        }
        .onReceive(documentStore.documentChangePublisher.replaceError(with: DocumentChange.collectionsUpdated([]))) { change in
            handleDocumentChange(change)
        }
        // Provider sheets (triggered from app menu or first launch)
        .sheet(isPresented: $appState.showAddProvider) {
            AddProviderSheet(
                onAdd: {
                    await appState.loadProviders()
                    appState.isFirstLaunchProviderSetup = false
                },
                isFirstLaunch: appState.isFirstLaunchProviderSetup
            )
        }
        .sheet(isPresented: $appState.showProvidersSettings) {
            ProvidersSettingsSheet()
                .environmentObject(appState)
        }
    }

    // MARK: - Content View (Middle Column)

    @ViewBuilder
    private var contentView: some View {
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
    private var detailView: some View {
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
    private var libraryDetailView: some View {
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
    private var libraryToolbar: some ToolbarContent {
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
    private func breadcrumbView(for doc: Document) -> some View {
        // TODO: Load ancestors from API via documentStore
        HStack(spacing: 4) {
            Text(doc.name)
                .fontWeight(.medium)
        }
    }

    // MARK: - Actions

    private func toggleSidebar() {
        withAnimation {
            if columnVisibility == .all {
                columnVisibility = .doubleColumn
            } else {
                columnVisibility = .all
            }
        }
    }

    /// Add a node from a tool definition to the current workflow
    private func addNodeFromTool(_ tool: ToolInfo, at position: CGPoint) {
        let newNode = WorkflowNode(from: tool, positionX: position.x, positionY: position.y)
        editingWorkflow.nodes.append(newNode)
        NSLog("[ContentView] Added node '\(tool.displayName)' at (\(position.x), \(position.y))")
    }

    // MARK: - Navigation

    private func navigateToDocument(_ doc: Document) {
        viewMode = .library(doc)
        if let item = findSidebarItem(for: doc, in: libraryItems) {
            selectedSidebarItem = item
        }
    }

    private func findSidebarItem(for doc: Document, in items: [SidebarItem]) -> SidebarItem? {
        for item in items {
            if case .document(let itemDoc) = item.itemType, itemDoc.id == doc.id {
                return item
            }
            if let children = item.children,
               let found = findSidebarItem(for: doc, in: children) {
                return found
            }
        }
        return nil
    }

    // MARK: - Conversations

    private func refreshConversations() {
        Task {
            do {
                let updated = try await conversationService.getConversationsForSidebar()
                await MainActor.run {
                    conversations = updated
                }
            } catch {
                NSLog("[ContentView] Failed to refresh conversations: %@", error.localizedDescription)
            }
        }
    }

    // MARK: - Saved Searches

    private func refreshSavedSearches() {
        Task {
            do {
                let updated = try await savedSearchService.getSavedSearchesForSidebar()
                await MainActor.run {
                    savedSearches = updated
                }
            } catch {
                NSLog("[ContentView] Failed to refresh saved searches: %@", error.localizedDescription)
            }
        }
    }
}

// MARK: - Preview

#Preview("Library Mode") {
    ContentView()
        .environmentObject(ViewSettings())
        .frame(width: 1200, height: 700)
}
