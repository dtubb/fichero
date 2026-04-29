import FicheroAPIClient
import OSLog
import SwiftUI

let libraryManagerLogger = Logger(subsystem: "com.fichero.fichero", category: "LibraryManager")

/// Manages multiple open .fichero libraries
/// Allows multiple windows and tabs to reference the same library instance
@MainActor
class LibraryManager: ObservableObject {
    static let shared = LibraryManager()

    /// Fixed UUID for the Global library (cross-library searches, chats, workflows)
    static let globalLibraryId = UUID(uuidString: "00000000-0000-0000-0000-000000000001")!

    /// All currently open libraries (Global is always last)
    @Published var openLibraries: [LibraryReference] = []

    /// The currently active library (used for new tabs/windows)
    @Published var currentLibraryId: UUID?

    /// Counter for unsaved library numbering (Untitled, Untitled 2, Untitled 3, etc.)
    var untitledCounter: Int = 1

    /// Represents an open library with its associated resources
    /// Each library has one instance of each service, shared across all windows/tabs viewing this library
    @MainActor
    class LibraryReference: Identifiable, ObservableObject {
        let id: UUID
        let url: URL
        @Published var displayName: String  // Display name for window title (e.g., "Untitled 2", "MyResearch")
        @Published var document: FicheroDocument

        // Core services - one instance per library, shared across all tabs/windows
        let apiClient: APIClient
        let ficheroClient: FicheroClient  // Generated API client
        let documentStore: DocumentStore
        let savedSearchServiceGenerated: SavedSearchServiceGenerated  // Generated saved search service
        let searchService: SearchServiceGenerated
        let conversationServiceGenerated: ConversationServiceGenerated  // Generated conversation service
        let chatServiceGenerated: ChatServiceGenerated  // Generated chat service
        let workflowStore: WorkflowStore
        let workflowServiceGenerated: WorkflowServiceGenerated  // Generated workflow service
        let workflowStreamService: WorkflowStreamService  // SSE streaming for workflow execution
        let importService: ImportServiceGenerated
        let documentServiceGenerated: DocumentServiceGenerated
        let storageService: StorageServiceGenerated
        let providerService: ProviderServiceGenerated
        let modelService: ModelServiceGenerated
        let artifactService: ArtifactServiceGenerated
        let entityService: EntityServiceGenerated  // /api/entities + /api/claims (#728)
        let activityService: ActivityServiceGenerated
        let batchService: BatchServiceGenerated
        let automationService: AutomationServiceGenerated
        let chainService: ChainService

        // Security-scoped resource tracking
        private nonisolated(unsafe) var isAccessingSecurityScope: Bool = false

        @MainActor
        init(
            url: URL,
            document: FicheroDocument,
            displayName: String,
            id: UUID? = nil,
            apiClient: APIClient? = nil,
            documentStore: DocumentStore? = nil,
            searchService: SearchServiceGenerated? = nil,
            workflowStore: WorkflowStore? = nil,
            importService: ImportServiceGenerated? = nil,
            storageService: StorageServiceGenerated? = nil,
            providerService: ProviderServiceGenerated? = nil,
            modelService: ModelServiceGenerated? = nil,
            startAccessing: Bool = false
        ) {
            self.id = id ?? UUID()
            self.url = url
            self.displayName = displayName
            self.document = document

            // Reuse existing instances or create new ones
            if let existingClient = apiClient {
                self.apiClient = existingClient
            } else {
                self.apiClient = APIClient()
            }

            // Set the library path on the API client immediately
            // This ensures all services created below have access to the path
            self.apiClient.currentLibraryPath = url.path

            // Create the generated API client (shares same library path)
            self.ficheroClient = FicheroClient(libraryPath: url.path)

            // Initialize all services with the library's APIClient
            self.documentStore = documentStore ?? DocumentStore(apiClient: self.apiClient)
            self.savedSearchServiceGenerated = SavedSearchServiceGenerated(ficheroClient: self.ficheroClient)
            self.searchService = searchService ?? SearchServiceGenerated(ficheroClient: self.ficheroClient)
            self.conversationServiceGenerated = ConversationServiceGenerated(ficheroClient: self.ficheroClient)
            self.chatServiceGenerated = ChatServiceGenerated(ficheroClient: self.ficheroClient)
            self.workflowStore = workflowStore ?? WorkflowStore(ficheroClient: self.ficheroClient)
            self.workflowServiceGenerated = WorkflowServiceGenerated(ficheroClient: self.ficheroClient)
            self.workflowStreamService = WorkflowStreamService(apiClient: self.apiClient)
            self.importService = importService ?? ImportServiceGenerated(ficheroClient: self.ficheroClient)
            self.documentServiceGenerated = DocumentServiceGenerated(ficheroClient: self.ficheroClient)
            self.storageService = storageService ?? StorageServiceGenerated(ficheroClient: self.ficheroClient)
            self.providerService = providerService ?? ProviderServiceGenerated(ficheroClient: self.ficheroClient)
            self.modelService = modelService ?? ModelServiceGenerated(ficheroClient: self.ficheroClient)
            self.artifactService = ArtifactServiceGenerated(ficheroClient: self.ficheroClient)
            self.entityService = EntityServiceGenerated(ficheroClient: self.ficheroClient)
            self.activityService = ActivityServiceGenerated(ficheroClient: self.ficheroClient)
            self.batchService = BatchServiceGenerated(ficheroClient: self.ficheroClient)
            self.automationService = AutomationServiceGenerated(ficheroClient: self.ficheroClient)
            self.chainService = ChainService(apiClient: self.apiClient)

            // Start accessing security-scoped resource if requested
            if startAccessing {
                self.startAccessingSecurityScope()
            }
        }

        /// Start accessing the security-scoped resource
        nonisolated func startAccessingSecurityScope() {
            guard !isAccessingSecurityScope else { return }
            if url.startAccessingSecurityScopedResource() {
                isAccessingSecurityScope = true
            }
        }

        /// Stop accessing the security-scoped resource
        nonisolated func stopAccessingSecurityScope() {
            guard isAccessingSecurityScope else { return }
            url.stopAccessingSecurityScopedResource()
            isAccessingSecurityScope = false
        }

        deinit {
            stopAccessingSecurityScope()
        }
    }

    private init() {
        // Always load Global library on startup
        loadGlobalLibrary()
    }

    /// Load or create the Global library
    /// Global library is stored at ~/Library/Application Support/com.fichero.fichero/global.fichero
    private func loadGlobalLibrary() {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let globalURL = appSupport
            .appendingPathComponent("com.fichero.fichero")
            .appendingPathComponent("global.fichero")

        // Check if Global library already exists
        if openLibraries.contains(where: { $0.id == Self.globalLibraryId }) {
            libraryManagerLogger.info("Global library already loaded")
            return
        }

        // Create package structure if needed
        createPackageStructure(at: globalURL)

        // Load or create Global library document
        let document = FicheroDocument()

        // Create Local library reference with fixed ID
        // Note: apiClient.currentLibraryPath is set in LibraryReference.init()
        let library = LibraryReference(
            url: globalURL,
            document: document,
            displayName: "Local",
            id: Self.globalLibraryId,
            startAccessing: false  // No security-scoped access needed for app support folder
        )

        // Always insert Global at the beginning
        openLibraries.insert(library, at: 0)

        libraryManagerLogger.info("Loaded Global library at: \(globalURL.path)")

        // Initialize backend database, load data, then ensure Inbox folder exists
        Task { @MainActor in
            await initializeBackendDatabase(for: library)
            await loadLibraryData(for: library)
            await ensureInboxFolder(for: library)
        }
    }

    /// Get the Global library (always available)
    var globalLibrary: LibraryReference? {
        return openLibraries.first(where: { $0.id == Self.globalLibraryId })
    }
}

enum LibraryError: Error {
    case libraryNotFound
    case saveFailed
    case loadFailed
}
