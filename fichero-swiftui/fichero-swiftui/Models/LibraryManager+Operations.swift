import SwiftUI
import OSLog
import FicheroAPIClient

extension LibraryManager {

    /// Open a library from a URL
    /// If already open, returns the existing reference
    /// - Parameter url: URL to the .fichero package
    /// - Returns: Library reference that can be shared across windows
    func openLibrary(at url: URL) -> LibraryReference {
        // Check if already open
        if let existing = openLibraries.first(where: { $0.url == url }) {
            libraryManagerLogger.info("Library already open: \(url.lastPathComponent)")
            return existing
        }

        // Create document for this library (state is managed by backend)
        let document = FicheroDocument()

        // Extract display name from file URL (remove .fichero extension)
        let displayName = url.deletingPathExtension().lastPathComponent

        // Determine if this is a user-opened library (needs security-scoped access)
        let needsSecurityAccess = !isTemporaryLibrary(url)

        // Create new library reference
        // Note: apiClient.currentLibraryPath is set in LibraryReference.init()
        let library = LibraryReference(
            url: url,
            document: document,
            displayName: displayName,
            startAccessing: needsSecurityAccess
        )

        // Insert after Global library (which is always first)
        if openLibraries.first?.id == Self.globalLibraryId {
            openLibraries.insert(library, at: 1)
        } else {
            openLibraries.append(library)
        }

        currentLibraryId = library.id  // Set as current library
        let clientId = ObjectIdentifier(library.apiClient)
        let securityScoped = needsSecurityAccess
        libraryManagerLogger.info("""
            Opened library: \(url.lastPathComponent, privacy: .public) \
            with APIClient-\(String(describing: clientId), privacy: .public) \
            (security-scoped: \(securityScoped))
            """)

        // Save open libraries for restoration on next launch
        saveOpenLibraryPaths()

        // Initialize the backend database connection, load data, and ensure Inbox
        Task { @MainActor in
            await initializeBackendDatabase(for: library)
            await loadLibraryData(for: library)
            await ensureInboxFolder(for: library)
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

        // Note: apiClient.currentLibraryPath is set in LibraryReference.init()
        let library = LibraryReference(url: temporaryURL, document: document, displayName: displayName)

        // Insert after Global library (which is always first)
        if openLibraries.first?.id == Self.globalLibraryId {
            openLibraries.insert(library, at: 1)
        } else {
            openLibraries.append(library)
        }

        currentLibraryId = library.id  // Set as current library

        // Increment counter for next new library
        untitledCounter += 1

        let clientId = ObjectIdentifier(library.apiClient)
        let clientIdStr = String(describing: clientId)
        libraryManagerLogger.info("Created new unsaved library '\(displayName)' with APIClient-\(clientIdStr)")

        // Persist open libraries so newly-created databases can be restored on next launch.
        saveOpenLibraryPaths()

        // Initialize the backend database, load data, and ensure Inbox
        Task { @MainActor in
            await initializeBackendDatabase(for: library)
            await loadLibraryData(for: library)
            await ensureInboxFolder(for: library)
        }

        return library
    }

    /// Get a library by ID
    func getLibrary(id: UUID) -> LibraryReference? {
        return openLibraries.first(where: { $0.id == id })
    }

    /// Close a library
    /// Only closes if no windows are using it
    /// Cannot close the Global library
    func closeLibrary(_ id: UUID) {
        // Prevent closing Global library
        if id == Self.globalLibraryId {
            libraryManagerLogger.warning("Cannot close Global library")
            return
        }

        guard let index = openLibraries.firstIndex(where: { $0.id == id }) else {
            return
        }

        let library = openLibraries[index]
        libraryManagerLogger.info("Closing library: \(library.url.lastPathComponent)")

        // Stop accessing security-scoped resource before removing
        library.stopAccessingSecurityScope()

        openLibraries.remove(at: index)

        // Update saved libraries
        saveOpenLibraryPaths()
    }

    // Save a library to a new URL (for Save As or initial save)
    // swiftlint:disable:next function_body_length
    func saveLibrary(_ id: UUID, to url: URL) throws {
        guard let index = openLibraries.firstIndex(where: { $0.id == id }) else {
            throw LibraryError.libraryNotFound
        }

        let oldLibrary = openLibraries[index]
        let oldURL = oldLibrary.url
        let fileManager = FileManager.default

        // Start accessing security-scoped resource from save panel
        let didStartAccessing = url.startAccessingSecurityScopedResource()
        libraryManagerLogger.info("Security-scoped resource access: \(didStartAccessing)")
        defer {
            if didStartAccessing {
                url.stopAccessingSecurityScopedResource()
            }
        }

        // Check if this is a temporary library
        let isTempLibrary = isTemporaryLibrary(oldURL)

        do {
            libraryManagerLogger.info("Old URL: \(oldURL.path)")
            libraryManagerLogger.info("New URL: \(url.path)")
            libraryManagerLogger.info("Is temporary library: \(isTempLibrary)")
            libraryManagerLogger.info("Old URL exists: \(fileManager.fileExists(atPath: oldURL.path))")

            if isTempLibrary && fileManager.fileExists(atPath: oldURL.path) {
                // Temporary libraries can be moved from sandbox temp dir
                libraryManagerLogger.info("Moving temporary library from \(oldURL.path) to \(url.path)")

                // Check if destination already exists
                if fileManager.fileExists(atPath: url.path) {
                    libraryManagerLogger.warning("Destination exists, removing: \(url.path)")
                    try fileManager.removeItem(at: url)
                }

                // Move the entire package directory
                try fileManager.moveItem(at: oldURL, to: url)
                libraryManagerLogger.info(
                    "Successfully moved package from \(oldURL.lastPathComponent) to \(url.lastPathComponent)"
                )

            } else {
                // Not a temp library, create new package (for Save As on already-saved libraries)
                createPackageStructure(at: url)
                libraryManagerLogger.info("Created new package at: \(url.lastPathComponent)")
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
            library.ficheroClient.currentLibraryPath = url.path

            // Update the reference in our array
            openLibraries[index] = library
            libraryManagerLogger.info("Saved library to: \(url.lastPathComponent)")

            // If we moved from temp, backend will reconnect automatically on next request
            // If we created new (Save As on already-saved library), initialize the database
            if !isTempLibrary {
                Task { @MainActor in
                    await initializeBackendDatabase(for: library)
                }
            }

        } catch {
            libraryManagerLogger.error("Failed to save library: \(error.localizedDescription)")
            throw LibraryError.saveFailed
        }
    }
}
