import SwiftUI
import Combine
import UniformTypeIdentifiers
import AppKit

/// ViewModel for managing sidebar state and business logic
@MainActor
class SidebarViewModel: ObservableObject {
    // MARK: - State
    @Published var state: SidebarState = SidebarState()
    
    // MARK: - Dependencies (injected)
    weak var documentStore: DocumentStore?
    weak var searchService: SavedSearchService?
    weak var conversationService: ConversationService?
    weak var workflowService: WorkflowService?
    weak var documentService: DocumentService?
    weak var errorService: ErrorService?
    weak var performanceService: PerformanceService?
    
    // MARK: - Drag and Drop
    @Published var dragDropModel: DragDropModel
    @Published var dragDropService: DragDropService
    
    // MARK: - Bindings
    @Binding var viewMode: AppViewMode
    @Binding var selectedItem: SidebarItem?
    
    // MARK: - Section Data
    let libraryItems: [SidebarItem]
    let searchItems: [SidebarItem]
    let chatItems: [SidebarItem]
    let workflowItems: [SidebarItem]
    
    // MARK: - Callbacks
    var onCreateChatWithDocuments: (([String]) -> Void)?
    
    // MARK: - Initialization
    init(
        viewMode: Binding<AppViewMode>,
        selectedItem: Binding<SidebarItem?>, 
        libraryItems: [SidebarItem],
        searchItems: [SidebarItem],
        chatItems: [SidebarItem],
        workflowItems: [SidebarItem],
        dragDropModel: DragDropModel,
        documentStore: DocumentStore? = nil,
        searchService: SavedSearchService? = nil,
        conversationService: ConversationService? = nil,
        workflowService: WorkflowService? = nil,
        documentService: DocumentService? = nil,
        errorService: ErrorService? = nil,
        performanceService: PerformanceService? = nil
    ) {
        self._viewMode = viewMode
        self._selectedItem = selectedItem
        self.libraryItems = libraryItems
        self.searchItems = searchItems
        self.chatItems = chatItems
        self.workflowItems = workflowItems
        self.documentStore = documentStore
        self.searchService = searchService
        self.conversationService = conversationService
        self.workflowService = workflowService
        self.documentService = documentService
        self.errorService = errorService
        self.performanceService = performanceService
        self.dragDropModel = dragDropModel
        self.dragDropService = DragDropService(dragDropModel: dragDropModel)
        self.searchService = searchService
        self.conversationService = conversationService
        self.workflowService = workflowService
        self.documentService = documentService
        self.errorService = errorService
        self.performanceService = performanceService
        
        setupSubscriptions()
    }
    
    // MARK: - Setup
    private func setupSubscriptions() {
        // Subscribe to document changes
        documentStore?.documentChangePublisher
            .catch { _ in Empty(completeImmediately: true) }
            .receive(on: DispatchQueue.main)
            .sink { [weak self] change in
                self?.handleDocumentChange(change)
            }
            .store(in: &cancellables)
        
        // Subscribe to drag and drop state changes
        setupDragDropSubscriptions()
    }
    
    private func setupDragDropSubscriptions() {
        // Subscribe to drag and drop model changes
        dragDropModel.objectWillChange
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                self?.syncDragDropState()
            }
            .store(in: &cancellables)
    }
    
    private func syncDragDropState() {
        state.isProcessingDrop = dragDropModel.isProcessingDrop
        state.dropProgress = dragDropModel.dropProgress
        state.dropErrorMessage = dragDropModel.dropError?.message
        state.dropSuccessCount = dragDropModel.dropSuccessCount
        state.dropFailureCount = dragDropModel.dropFailureCount
    }
    
    // MARK: - Dependency Injection
    func injectDependencies(
        documentStore: DocumentStore,
        searchService: SavedSearchService,
        conversationService: ConversationService,
        workflowService: WorkflowService,
        documentService: DocumentService,
        errorService: ErrorService,
        performanceService: PerformanceService
    ) {
        self.documentStore = documentStore
        self.searchService = searchService
        self.conversationService = conversationService
        self.workflowService = workflowService
        self.documentService = documentService
        self.errorService = errorService
        self.performanceService = performanceService
        
        // Inject dependencies into drag and drop service
        dragDropService.injectDependencies(
            documentStore: documentStore,
            errorService: errorService,
            performanceService: performanceService
        )
        
        // Re-setup subscriptions with new dependencies
        setupSubscriptions()
    }
    
    // MARK: - State Management
    private var cancellables = Set<AnyCancellable>()
    
    // MARK: - Document Change Handling
    private func handleDocumentChange(_ change: DocumentChange) {
        switch change {
        case .collectionsUpdated:
            // Update handled by parent view recomputing libraryItems
            break

        case .collectionSelected(let collection):
            // Update selection if the selected collection is in our library items
            if let item = libraryItems.first(where: { $0.id == collection.id }) {
                selectedItem = item
            }

        case .documentsUpdated:
            // Update handled by parent view
            break

        case .documentDeleted:
            // Remove deleted document from UI
            // Note: The parent view will recompute libraryItems, but we can also handle it here
            // for immediate feedback
            break
        case .documentCreated:
            // New document created - parent view will recompute libraryItems
            break
        }
    }
    
    // MARK: - Selection Handling
    func handleSelection(_ item: SidebarItem?) {
        guard let item = item else { return }

        switch item.itemType {
        case .document(let doc):
            viewMode = .library(doc)
        case .savedSearch(let search):
            viewMode = .search(search)
        case .conversation(let conversation):
            viewMode = .chat(conversation)
        case .workflow(let workflow):
            viewMode = .workflow(workflow)
        case .sectionHeader:
            // No action needed for section headers
            return
        }
    }
    
    // MARK: - Folder Creation
    func createNewFolder(name: String) async throws -> Document {
        guard let section = state.newFolderSection else {
            throw NSError(domain: "com.fichero.sidebar",
                         code: 1,
                         userInfo: [NSLocalizedDescriptionKey: "No section specified for folder creation"])
        }

        // Create the folder using the appropriate service based on section
        let newFolder: Document
        switch section {
        case .library:
            newFolder = try await documentService!.createFolder(name: name, parentId: state.newFolderParentId)
        case .searches:
            // For searches, we'll create a folder in the searches section
            newFolder = try await documentService!.createFolder(name: name, parentId: state.newFolderParentId)
        case .chat:
            // For chat, we'll create a folder in the conversations section
            newFolder = try await documentService!.createFolder(name: name, parentId: state.newFolderParentId)
        case .workflows:
            // For workflows, we'll create a folder in the workflows section
            newFolder = try await documentService!.createFolder(name: name, parentId: state.newFolderParentId)
        }

        // Reset folder creation state
        state.resetFolderCreationState()
        
        return newFolder
    }
    
    /// Create a new folder inline (for the sheet dialog)
    func createNewFolderInline() async {
        guard let section = state.newFolderSection else {
            let error = ErrorModel.validationError(
                message: "No section specified for folder creation",
                context: ["operation": "create_folder"]
            )
            errorService?.reportError(error, showUserFeedback: false)
            state.newFolderErrorMessage = error.message
            return
        }

        guard !state.newFolderName.isEmpty else {
            let error = ErrorModel.validationError(
                message: "Folder name cannot be empty",
                context: ["operation": "create_folder", "section": section.rawValue]
            )
            errorService?.reportError(error, showUserFeedback: false)
            state.newFolderErrorMessage = error.message
            return
        }

        state.isCreatingFolder = true
        state.newFolderErrorMessage = nil

        do {
            let newFolder = try await createNewFolder(name: state.newFolderName)
            state.showingNewFolderDialog = false
            state.newFolderName = ""
            
            // Show success alert
            if let window = NSApp.keyWindow {
                let alert = NSAlert()
                alert.messageText = "Folder Created"
                alert.informativeText = "Folder created successfully"
                alert.addButton(withTitle: "OK")
                alert.beginSheetModal(for: window, completionHandler: nil)
            }
        } catch {
            let errorModel = ErrorModel.fileSystemError(
                message: "Failed to create folder: \((error.localizedDescription))",
                context: [
                    "operation": "create_folder",
                    "folder_name": state.newFolderName,
                    "section": section.rawValue
                ],
                isRecoverable: true
            )
            errorService?.reportError(errorModel)
            state.newFolderErrorMessage = errorModel.message
        }

        state.isCreatingFolder = false
    }
    
    // MARK: - Navigation Actions
    func createNewSearch() {
        viewMode = .search(nil)
    }

    func createNewChat() {
        viewMode = .chat(nil)
    }

    func createNewWorkflow() {
        viewMode = .workflow(nil)
    }
    
    // MARK: - Drop Handling
    func handleChatDrop(providers: [NSItemProvider]) -> Bool {
        dragDropService.handleChatDrop(providers: providers) { documentIds in
            self.createNewChatWithDocuments(documentIds)
        }
        return true
    }

    func createNewChatWithDocuments(_ documentIds: [String]) {
        viewMode = .chat(nil)
        onCreateChatWithDocuments?(documentIds)
    }
    
    /// Handle drop on Library section (create new collection with imported files)
    func handleLibrarySectionDrop(providers: [NSItemProvider]) -> Bool {
        var handled = false
        dragDropService.handleLibrarySectionDrop(providers: providers) { success in
            handled = success
        }
        return handled
    }
    
    
    // MARK: - Expansion State Management
    func toggleSectionExpansion(_ section: SidebarSection) {
        switch section {
        case .library:
            state.libraryExpanded.toggle()
        case .searches:
            state.searchesExpanded.toggle()
        case .chat:
            state.chatExpanded.toggle()
        case .workflows:
            state.workflowsExpanded.toggle()
        }
    }
    
    func isSectionExpanded(_ section: SidebarSection) -> Bool {
        switch section {
        case .library:
            return state.libraryExpanded
        case .searches:
            return state.searchesExpanded
        case .chat:
            return state.chatExpanded
        case .workflows:
            return state.workflowsExpanded
        }
    }
    
    func toggleItemExpansion(_ itemId: String) {
        if state.expandedItems.contains(itemId) {
            state.expandedItems.remove(itemId)
        } else {
            state.expandedItems.insert(itemId)
        }
    }
    
    func isItemExpanded(_ itemId: String) -> Bool {
        return state.expandedItems.contains(itemId)
    }
    
    // MARK: - Performance Monitoring
    func startPerformanceMonitoring() {
        performanceService?.startFrameRateMonitoring("sidebar")
        performanceService?.recordMemoryMeasurement("sidebar_initial")
    }
    
    func stopPerformanceMonitoring() {
        if let result = performanceService?.stopFrameRateMonitoring("sidebar") {
        }
    }
}