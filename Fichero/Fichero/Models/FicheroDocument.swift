import SwiftUI
import UniformTypeIdentifiers

/// A Fichero library document
/// Each .fichero file represents a complete library with its own database, storage, and vector embeddings
/// Similar to how DEVONthink or Bookends manages separate databases
struct FicheroDocument: FileDocument, Codable {
    // MARK: - FileDocument Conformance

    static var readableContentTypes: [UTType] = [.ficheroSession]

    // MARK: - Library Identity

    /// Unique library identifier (used for database/storage paths)
    var libraryId: UUID

    /// User-facing library name (displayed in title bar, file browser)
    var libraryName: String

    /// Creation date of this library
    var libraryCreatedAt: Date

    // MARK: - Session State

    /// Unique session identifier (for this specific window/tab instance)
    var sessionId: UUID

    /// Current view mode for this tab/window
    var viewMode: ViewMode

    /// Context for each view mode (only one is active at a time)
    var libraryContext: LibraryContext?
    var workflowContext: WorkflowContext?
    var chatContext: ChatContext?
    var searchContext: SearchContext?

    /// Document metadata
    var createdAt: Date
    var lastModified: Date

    // MARK: - Initialization

    init(
        libraryId: UUID = UUID(),
        libraryName: String = "New Library",
        libraryCreatedAt: Date = Date(),
        sessionId: UUID = UUID(),
        viewMode: ViewMode = .library,
        createdAt: Date = Date(),
        lastModified: Date = Date()
    ) {
        self.libraryId = libraryId
        self.libraryName = libraryName
        self.libraryCreatedAt = libraryCreatedAt
        self.sessionId = sessionId
        self.viewMode = viewMode
        self.createdAt = createdAt
        self.lastModified = lastModified

        // Initialize context for the current view mode
        switch viewMode {
        case .library:
            self.libraryContext = LibraryContext()
        case .workflow:
            self.workflowContext = WorkflowContext()
        case .chat:
            self.chatContext = ChatContext()
        case .search:
            self.searchContext = SearchContext()
        }
    }

    // MARK: - FileDocument Protocol

    init(configuration: ReadConfiguration) throws {
        // Read from package directory
        guard let documentWrapper = configuration.file.fileWrappers?["document.json"],
              let data = documentWrapper.regularFileContents else {
            throw CocoaError(.fileReadCorruptFile)
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601

        self = try decoder.decode(FicheroDocument.self, from: data)
    }

    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]

        // Encode document metadata to JSON
        let data = try encoder.encode(self)
        let documentFile = FileWrapper(regularFileWithContents: data)
        documentFile.preferredFilename = "document.json"

        // Create package directory structure
        var fileWrappers: [String: FileWrapper] = [
            "document.json": documentFile
        ]

        // Preserve existing database, lance, storage, files if they exist
        if let existingWrapper = configuration.existingFile {
            if let duckdb = existingWrapper.fileWrappers?["fichero.duckdb"] {
                fileWrappers["fichero.duckdb"] = duckdb
            }
            if let lance = existingWrapper.fileWrappers?["lance"] {
                fileWrappers["lance"] = lance
            } else {
                // Create empty lance directory if it doesn't exist
                fileWrappers["lance"] = FileWrapper(directoryWithFileWrappers: [:])
            }
            if let storage = existingWrapper.fileWrappers?["storage"] {
                fileWrappers["storage"] = storage
            } else {
                // Create empty storage directory
                fileWrappers["storage"] = FileWrapper(directoryWithFileWrappers: [:])
            }
            if let files = existingWrapper.fileWrappers?["files"] {
                fileWrappers["files"] = files
            } else {
                // Create empty files directory
                fileWrappers["files"] = FileWrapper(directoryWithFileWrappers: [:])
            }
        } else {
            // New document - create empty directories
            fileWrappers["lance"] = FileWrapper(directoryWithFileWrappers: [:])
            fileWrappers["storage"] = FileWrapper(directoryWithFileWrappers: [:])
            fileWrappers["files"] = FileWrapper(directoryWithFileWrappers: [:])
        }

        // Create package directory wrapper
        let packageWrapper = FileWrapper(directoryWithFileWrappers: fileWrappers)
        return packageWrapper
    }

    // MARK: - Codable

    enum CodingKeys: String, CodingKey {
        case libraryId
        case libraryName
        case libraryCreatedAt
        case sessionId
        case viewMode
        case libraryContext
        case workflowContext
        case chatContext
        case searchContext
        case createdAt
        case lastModified
    }

    // MARK: - Package Path Helpers

    /// Container for package document paths
    struct PackagePaths {
        let databasePath: URL
        let lanceDBPath: URL
        let storagePath: URL
        let filesPath: URL
    }

    /// Get paths within the package document
    /// - Parameter packageURL: URL of the .fichero package (the document's file URL)
    /// - Returns: Paths for database, lance, storage, and files directories
    func packagePaths(for packageURL: URL) -> PackagePaths {
        return PackagePaths(
            databasePath: packageURL.appendingPathComponent("fichero.duckdb"),
            lanceDBPath: packageURL.appendingPathComponent("lance"),
            storagePath: packageURL.appendingPathComponent("storage"),
            filesPath: packageURL.appendingPathComponent("files")
        )
    }
}

// MARK: - View Mode

enum ViewMode: String, Codable {
    case library
    case workflow
    case chat
    case search

    var displayName: String {
        switch self {
        case .library: return "Library"
        case .workflow: return "Workflow"
        case .chat: return "Chat"
        case .search: return "Search"
        }
    }

    var systemImage: String {
        switch self {
        case .library: return "folder"
        case .workflow: return "arrow.triangle.branch"
        case .chat: return "bubble.left.and.bubble.right"
        case .search: return "magnifyingglass"
        }
    }
}

// MARK: - UTType Extension

extension UTType {
    /// Custom UTType for Fichero library package documents
    /// Package documents appear as single files but are actually directories
    /// Similar to .keynote, .pages, .sketch, .logic files
    static var ficheroSession: UTType {
        UTType(exportedAs: "ca.tubb.fichero.library", conformingTo: .package)
    }
}
