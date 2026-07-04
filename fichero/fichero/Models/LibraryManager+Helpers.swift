import FicheroAPIClient
import OSLog
import SwiftUI

extension LibraryManager {

    // MARK: - Public Helpers

    /// Check if a library URL is a temporary unsaved library
    /// Uses standardized paths to prevent path traversal attacks
    func isTemporaryLibrary(_ url: URL) -> Bool {
        let tempDir = FileManager.default.temporaryDirectory.standardizedFileURL
        let standardizedURL = url.standardizedFileURL

        // Ensure the path doesn't contain directory traversal
        guard !standardizedURL.path.contains("..") else {
            return false
        }

        return standardizedURL.path.hasPrefix(tempDir.path) &&
            standardizedURL.lastPathComponent.hasPrefix("Untitled-")
    }

    // MARK: - Internal Helpers

    /// Called after EmbeddedBackendService has connected to either the external
    /// development engine or the bundled engine. Until this point, restored
    /// libraries exist as UI state only and do not fire API requests (#1163).
    func backendDidBecomeReady() async {
        backendIsReady = true
        for library in openLibraries {
            library.reconfigureBackendHost()
            await loadLibraryDataIfNeeded(for: library)
        }
    }

    /// The library-side effects that fire when the engine reaches `.ready`,
    /// shared by BOTH platforms (#3113): refresh the known-library registry,
    /// adopt a paired remote library (self-guarded — a no-op unless the host is
    /// external), then reload every open library's data. This is the ONE place
    /// the ready transition hangs its side effects, replacing the copy in
    /// `FicheroApp.connectBackend` and `FicheroApp_iOS.reconnectToConfiguredHost`.
    /// The heartbeat (AppState) and iOS capture-queue resume layer on in the
    /// callers, since those aren't library concerns.
    func refreshAfterBackendBecameReady() async {
        await KnownLibraryRegistryStore.shared.refresh()
        adoptPairedRemoteLibrary()
        await backendDidBecomeReady()
    }

    func reconfigureGeneratedClientsForCurrentHost() {
        for library in openLibraries {
            library.reconfigureBackendHost()
        }
    }

    /// Remote clients use only the library path explicitly advertised by the
    /// host's pairing payload. Do not infer from the host registry: registry
    /// entries are recents/known libraries, not the set currently open for
    /// remote use.
    func adoptPairedRemoteLibrary() {
        guard EngineConfig.requiresExternalBackendConnection else { return }
        let path = RemoteAccessConfig.pairedLibraryPath
        guard !path.isEmpty else { return }

        let remoteURL = URL(fileURLWithPath: path)
        if let current = globalLibrary, current.url.path == remoteURL.path {
            current.reconfigureBackendHost()
            return
        }

        let library = LibraryReference(
            url: remoteURL,
            document: FicheroDocument(),
            displayName: remoteURL.deletingPathExtension().lastPathComponent,
            id: Self.globalLibraryId,
            startAccessing: false
        )

        openLibraries.removeAll { $0.id == Self.globalLibraryId }
        openLibraries.insert(library, at: 0)
        currentLibraryId = library.id
        loadedLibraryIds.removeAll()
        loadingLibraryIds.removeAll()
        libraryManagerLogger.info("Adopted paired remote library: \(remoteURL.path, privacy: .public)")
    }

    /// Starts a library load immediately when the backend is ready, otherwise
    /// leaves it queued for backendDidBecomeReady().
    func scheduleLoadWhenBackendReady(for library: LibraryReference) {
        guard backendIsReady else {
            libraryManagerLogger.info("Deferring library load until backend ready: \(library.displayName)")
            return
        }

        Task { @MainActor in
            await loadLibraryDataIfNeeded(for: library)
        }
    }

    /// Initialize the backend database, load app data, and create Inbox once
    /// per library. Re-entrant guards avoid duplicate startup tasks when the
    /// window, restore, and backend-ready paths all observe the same library.
    func loadLibraryDataIfNeeded(for library: LibraryReference) async {
        guard !loadedLibraryIds.contains(library.id),
              !loadingLibraryIds.contains(library.id) else {
            return
        }

        loadingLibraryIds.insert(library.id)
        defer { loadingLibraryIds.remove(library.id) }

        await initializeBackendDatabase(for: library)
        await loadLibraryData(for: library)
        await ensureInboxFolder(for: library)
        loadedLibraryIds.insert(library.id)
        librariesLoadVersion += 1
    }

    /// Create the .fichero package directory structure
    func createPackageStructure(at url: URL) {
        let fileManager = FileManager.default

        do {
            // Create the package directory if it doesn't exist
            if !fileManager.fileExists(atPath: url.path) {
                try fileManager.createDirectory(at: url, withIntermediateDirectories: true)
                libraryManagerLogger.info("Created .fichero package directory: \(url.path)")
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
                    <string>app.fichero.fichero.library</string>
                    <key>CFBundleName</key>
                    <string>\(url.deletingPathExtension().lastPathComponent)</string>
                </dict>
                </plist>
                """
                try plistContent.write(to: infoPlistURL, atomically: true, encoding: .utf8)
            }

            libraryManagerLogger.info("Package structure ready at: \(url.path)")

        } catch {
            libraryManagerLogger.error("Failed to create package structure: \(error.localizedDescription)")
        }
    }

    /// Initialize the backend database for a library
    func initializeBackendDatabase(for library: LibraryReference) async {
        do {
            let _: HealthResponse = try await library.apiClient.get("/health")
            libraryManagerLogger.info("Initialized backend database for: \(library.displayName)")
        } catch {
            libraryManagerLogger.error("Failed to initialize backend database: \(error.localizedDescription)")
        }
    }

    /// Load all data for a library (documents, searches, conversations, workflows)
    func loadLibraryData(for library: LibraryReference) async {
        libraryManagerLogger.info("⏱ loadLibraryData entry — library: \(library.displayName)")
        guard !Task.isCancelled else { return }
        await library.documentStore.loadCollections()
        let docCount = library.documentStore.collections.count
        libraryManagerLogger.info("⏱ loadLibraryData documents loaded (\(docCount) items)")

        guard !Task.isCancelled else { return }
        await library.workflowStore.loadWorkflows()
        libraryManagerLogger.info("⏱ loadLibraryData workflows loaded")

        guard !Task.isCancelled else { return }
        try? await library.conversationServiceGenerated.loadConversations()
        libraryManagerLogger.info("⏱ loadLibraryData conversations loaded")

        guard !Task.isCancelled else { return }
        try? await library.savedSearchServiceGenerated.loadSavedSearches()
        libraryManagerLogger.info("⏱ loadLibraryData exit — library: \(library.displayName)")
    }

    /// Ensure every library has a default "Inbox" folder
    func ensureInboxFolder(for library: LibraryReference) async {
        // Check if Inbox folder exists (collections should already be loaded)
        let hasInbox = library.documentStore.collections.contains { doc in
            doc.name == "Inbox" && doc.docType == .folder && doc.parentId == nil
        }

        let collectionCount = library.documentStore.collections.count
        libraryManagerLogger.info(
            "\(library.displayName) library has \(collectionCount) documents, hasInbox: \(hasInbox)"
        )

        if !hasInbox {
            // Create Inbox folder
            do {
                let inbox = try await library.documentServiceGenerated.createCollection(
                    name: "Inbox",
                    parentId: nil
                )
                libraryManagerLogger.info(
                    "Created default Inbox folder in \(library.displayName) library: \(inbox.id)"
                )

                // Reload documents to include the new Inbox
                await library.documentStore.loadCollections()
                let reloadedCount = library.documentStore.collections.count
                libraryManagerLogger.info("Reloaded collections, now have \(reloadedCount) documents")
            } catch {
                libraryManagerLogger.error(
                    "Failed to create Inbox folder in \(library.displayName): \(error.localizedDescription)"
                )
            }
        } else {
            libraryManagerLogger.info("Inbox folder already exists in \(library.displayName) library")
        }
    }
}
