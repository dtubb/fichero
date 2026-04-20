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
                    <string>com.tubb.fichero.library</string>
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
            struct HealthResponse: Codable {
                let status: String
            }
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
        libraryManagerLogger.info("⏱ loadLibraryData documents loaded (\(library.documentStore.collections.count) items)")

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
                    "✅ Created default Inbox folder in \(library.displayName) library: \(inbox.id)"
                )

                // Reload documents to include the new Inbox
                await library.documentStore.loadCollections()
                let reloadedCount = library.documentStore.collections.count
                libraryManagerLogger.info("Reloaded collections, now have \(reloadedCount) documents")
            } catch {
                libraryManagerLogger.error(
                    "❌ Failed to create Inbox folder in \(library.displayName): \(error.localizedDescription)"
                )
            }
        } else {
            libraryManagerLogger.info("Inbox folder already exists in \(library.displayName) library")
        }
    }
}
