import SwiftUI
import OSLog

/// Manages multiple open .fichero libraries
/// Allows multiple windows and tabs to reference the same library instance
@MainActor
class LibraryManager: ObservableObject {
    static let shared = LibraryManager()

    private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "LibraryManager")

    /// All currently open libraries
    @Published private(set) var openLibraries: [LibraryReference] = []

    /// The currently active library (used for new tabs/windows)
    @Published var currentLibraryId: UUID?

    /// Counter for unsaved library numbering (Untitled, Untitled 2, Untitled 3, etc.)
    private var untitledCounter: Int = 1

    /// Represents an open library with its associated resources
    class LibraryReference: Identifiable, ObservableObject {
        let id: UUID
        let url: URL
        let displayName: String  // Display name for window title (e.g., "Untitled 2", "MyResearch")
        @Published var document: FicheroDocument
        let apiClient: APIClient
        let documentStore: DocumentStore  // Shared across all windows/tabs for this library

        // Security-scoped resource tracking
        private var isAccessingSecurityScope: Bool = false

        @MainActor
        init(url: URL, document: FicheroDocument, displayName: String, id: UUID? = nil, apiClient: APIClient? = nil, documentStore: DocumentStore? = nil, startAccessing: Bool = false) {
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

            if let existingStore = documentStore {
                self.documentStore = existingStore
            } else {
                self.documentStore = DocumentStore(apiClient: self.apiClient)
            }

            // Start accessing security-scoped resource if requested
            if startAccessing {
                self.startAccessingSecurityScope()
            }
        }

        /// Start accessing the security-scoped resource
        func startAccessingSecurityScope() {
            guard !isAccessingSecurityScope else { return }
            if url.startAccessingSecurityScopedResource() {
                isAccessingSecurityScope = true
            }
        }

        /// Stop accessing the security-scoped resource
        func stopAccessingSecurityScope() {
            guard isAccessingSecurityScope else { return }
            url.stopAccessingSecurityScopedResource()
            isAccessingSecurityScope = false
        }

        deinit {
            stopAccessingSecurityScope()
        }
    }

    private init() {}

    /// Open a library from a URL
    /// If already open, returns the existing reference
    /// - Parameter url: URL to the .fichero package
    /// - Returns: Library reference that can be shared across windows
    func openLibrary(at url: URL) -> LibraryReference {
        // Check if already open
        if let existing = openLibraries.first(where: { $0.url == url }) {
            logger.info("Library already open: \(url.lastPathComponent)")
            return existing
        }

        // Load document from URL
        let document = FicheroDocument()
        // TODO: Actually load document data from URL
        // For now, just create empty document

        // Extract display name from file URL (remove .fichero extension)
        let displayName = url.deletingPathExtension().lastPathComponent

        // Determine if this is a user-opened library (needs security-scoped access)
        let needsSecurityAccess = !isTemporaryLibrary(url)

        // Create new library reference
        let library = LibraryReference(url: url, document: document, displayName: displayName, startAccessing: needsSecurityAccess)
        library.apiClient.currentLibraryPath = url.path

        openLibraries.append(library)
        currentLibraryId = library.id  // Set as current library
        let clientId = ObjectIdentifier(library.apiClient)
        logger.info("Opened library: \(url.lastPathComponent, privacy: .public) with APIClient-\(String(describing: clientId), privacy: .public) (security-scoped: \(needsSecurityAccess))")

        // Save open libraries for restoration on next launch
        saveOpenLibraryPaths()

        // Initialize the backend database connection
        Task {
            await initializeBackendDatabase(for: library)
        }

        return library
    }

    /// Create a new unsaved library
    /// - Returns: Library reference for a new library (not yet saved to disk)
    func createNewLibrary() -> LibraryReference {
        let document = FicheroDocument()

        // Generate Mac-style display name (Untitled, Untitled 2, Untitled 3, etc.)
        let displayName = untitledCounter == 1 ? "Untitled" : "Untitled \(untitledCounter)"

        // Each new library gets a unique temporary path so they're separate
        // Use FileManager.default.temporaryDirectory for sandbox compatibility
        let uuid = UUID().uuidString
        let temporaryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("Untitled-\(uuid).fichero")

        // Create the package structure even for temporary libraries
        // This ensures the backend database is created in the right place
        createPackageStructure(at: temporaryURL)

        let library = LibraryReference(url: temporaryURL, document: document, displayName: displayName)
        library.apiClient.currentLibraryPath = temporaryURL.path  // Set API client path

        openLibraries.append(library)
        currentLibraryId = library.id  // Set as current library

        // Increment counter for next new library
        untitledCounter += 1

        let clientId = ObjectIdentifier(library.apiClient)
        logger.info("Created new unsaved library '\(displayName)' with APIClient-\(String(describing: clientId))")

        // Initialize the backend database
        Task {
            await initializeBackendDatabase(for: library)
        }

        return library
    }

    /// Get a library by ID
    func getLibrary(id: UUID) -> LibraryReference? {
        return openLibraries.first(where: { $0.id == id })
    }

    /// Close a library
    /// Only closes if no windows are using it
    func closeLibrary(_ id: UUID) {
        guard let index = openLibraries.firstIndex(where: { $0.id == id }) else {
            return
        }

        let library = openLibraries[index]
        logger.info("Closing library: \(library.url.lastPathComponent)")

        // Stop accessing security-scoped resource before removing
        library.stopAccessingSecurityScope()

        openLibraries.remove(at: index)

        // Update saved libraries
        saveOpenLibraryPaths()
    }

    /// Save a library to a new URL (for Save As or initial save)
    func saveLibrary(_ id: UUID, to url: URL) throws {
        guard let index = openLibraries.firstIndex(where: { $0.id == id }) else {
            throw LibraryError.libraryNotFound
        }

        let oldLibrary = openLibraries[index]
        let oldURL = oldLibrary.url
        let fileManager = FileManager.default

        // Start accessing security-scoped resource from save panel
        let didStartAccessing = url.startAccessingSecurityScopedResource()
        logger.info("Security-scoped resource access: \(didStartAccessing)")
        defer {
            if didStartAccessing {
                url.stopAccessingSecurityScopedResource()
            }
        }

        // Check if this is a temporary library
        let isTempLibrary = isTemporaryLibrary(oldURL)

        do {
            logger.info("Old URL: \(oldURL.path)")
            logger.info("New URL: \(url.path)")
            logger.info("Is temporary library: \(isTempLibrary)")
            logger.info("Old URL exists: \(fileManager.fileExists(atPath: oldURL.path))")

            if isTempLibrary && fileManager.fileExists(atPath: oldURL.path) {
                // Temporary libraries can be moved from sandbox temp dir
                logger.info("Moving temporary library from \(oldURL.path) to \(url.path)")

                // Check if destination already exists
                if fileManager.fileExists(atPath: url.path) {
                    logger.warning("Destination exists, removing: \(url.path)")
                    try fileManager.removeItem(at: url)
                }

                // Move the entire package directory
                try fileManager.moveItem(at: oldURL, to: url)
                logger.info("Successfully moved package from \(oldURL.lastPathComponent) to \(url.lastPathComponent)")

            } else {
                // Not a temp library, create new package (for Save As on already-saved libraries)
                createPackageStructure(at: url)

                // TODO: Copy database and contents from oldURL to url if doing Save As
                logger.info("Created new package at: \(url.lastPathComponent)")
            }

            // Extract display name from new file URL (remove .fichero extension)
            let displayName = url.deletingPathExtension().lastPathComponent

            // Stop accessing old library's security-scoped resource if needed
            oldLibrary.stopAccessingSecurityScope()

            // Create new library reference with saved URL, preserving the ID and reusing APIClient/DocumentStore
            // Always need security-scoped access for user-saved libraries
            let library = LibraryReference(
                url: url,
                document: oldLibrary.document,
                displayName: displayName,
                id: oldLibrary.id,  // IMPORTANT: Preserve library ID so windows don't lose track
                apiClient: oldLibrary.apiClient,  // Reuse existing APIClient
                documentStore: oldLibrary.documentStore,  // Reuse existing DocumentStore
                startAccessing: true  // Always start accessing for saved libraries
            )

            // Update the API client's library path to the new location
            library.apiClient.currentLibraryPath = url.path

            // Update the reference in our array
            openLibraries[index] = library
            logger.info("Saved library to: \(url.lastPathComponent)")

            // If we moved from temp, backend will reconnect automatically on next request
            // If we created new (Save As on already-saved library), initialize the database
            if !isTempLibrary {
                Task {
                    await initializeBackendDatabase(for: library)
                }
            }

        } catch {
            logger.error("Failed to save library: \(error.localizedDescription)")
            throw LibraryError.saveFailed
        }
    }

    // MARK: - Public Helpers

    /// Check if a library URL is a temporary unsaved library
    func isTemporaryLibrary(_ url: URL) -> Bool {
        let tempDir = FileManager.default.temporaryDirectory
        return url.path.hasPrefix(tempDir.path) &&
               url.lastPathComponent.hasPrefix("Untitled-")
    }

    // MARK: - Private Helpers

    /// Create the .fichero package directory structure
    private func createPackageStructure(at url: URL) {
        let fileManager = FileManager.default

        do {
            // Create the package directory if it doesn't exist
            if !fileManager.fileExists(atPath: url.path) {
                try fileManager.createDirectory(at: url, withIntermediateDirectories: true)
                logger.info("Created .fichero package directory: \(url.path)")
            }

            // Create required subdirectories
            let contentsDir = url.appendingPathComponent("Contents")
            try fileManager.createDirectory(at: contentsDir, withIntermediateDirectories: true)

            // Create a simple plist to mark this as a package
            let infoPlistURL = contentsDir.appendingPathComponent("Info.plist")
            if !fileManager.fileExists(atPath: infoPlistURL.path) {
                let plistContent = """
                <?xml version="1.0" encoding="UTF-8"?>
                <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
                <plist version="1.0">
                <dict>
                    <key>CFBundleIdentifier</key>
                    <string>ca.tubb.fichero.library</string>
                    <key>CFBundleName</key>
                    <string>\(url.deletingPathExtension().lastPathComponent)</string>
                </dict>
                </plist>
                """
                try plistContent.write(to: infoPlistURL, atomically: true, encoding: .utf8)
            }

            logger.info("Package structure ready at: \(url.path)")

        } catch {
            logger.error("Failed to create package structure: \(error.localizedDescription)")
        }
    }

    /// Initialize the backend database for a library
    private func initializeBackendDatabase(for library: LibraryReference) async {
        do {
            struct HealthResponse: Codable {
                let status: String
            }
            let _: HealthResponse = try await library.apiClient.get("/health")
            logger.info("Initialized backend database for: \(library.displayName)")
        } catch {
            logger.error("Failed to initialize backend database: \(error.localizedDescription)")
        }
    }
}

enum LibraryError: Error {
    case libraryNotFound
    case saveFailed
    case loadFailed
}

// MARK: - Library Persistence

extension LibraryManager {
    private static let openLibraryPathsKey = "FicheroOpenLibraryPaths"

    /// Save current open library paths to UserDefaults
    func saveOpenLibraryPaths() {
        let paths = openLibraries
            .filter { !isTemporaryLibrary($0.url) }
            .map { $0.url.path }
        UserDefaults.standard.set(paths, forKey: Self.openLibraryPathsKey)
        logger.info("Saved \(paths.count) library paths to UserDefaults")
    }

    /// Get previously open library paths
    func getSavedLibraryPaths() -> [String] {
        return UserDefaults.standard.stringArray(forKey: Self.openLibraryPathsKey) ?? []
    }

    /// Restore libraries from saved paths
    func restoreSavedLibraries() {
        let paths = getSavedLibraryPaths()
        logger.info("Restoring \(paths.count) saved libraries")

        for path in paths {
            let url = URL(fileURLWithPath: path)
            if FileManager.default.fileExists(atPath: path) {
                let library = openLibrary(at: url)
                logger.info("Restored library: \(library.displayName)")
            } else {
                logger.warning("Saved library not found: \(path)")
            }
        }
    }
}
