import OSLog
import SwiftUI
import UniformTypeIdentifiers

// MARK: - ContentView Import & Service Actions

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ContentView")

extension ContentView {

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

    /// Run the query typed in the global toolbar search field.
    ///
    /// Searching is navigation, not an artifact (#4086): submitting a query
    /// persists nothing. And it is not a mode switch (#4106/S2): results
    /// render INTO the Library view — `viewMode` stays `.library`, and the
    /// library column's contents swap to the transient result set. Saving
    /// stays the explicit "Save Search" action.
    func runToolbarSearch(_ rawQuery: String) {
        guard featureManager.isSearchEnabled else { return }
        guard let route = ToolbarSearchRouter.route(for: rawQuery) else { return }

        sidebarSelectionState.selectedItemId = nil
        sidebarMode = route.sidebarMode
        viewMode = route.viewMode
        activeSearchQuery = route.query
        Task { @MainActor in
            await runTransientSearch(route.query)
        }
    }

    // MARK: - File Import

    func handleFileDrop(urls: [URL]) {
        logger.info("Files dropped: \(urls.map { $0.lastPathComponent })")

        let droppedURLs = classifyDroppedURLs(urls)
        openDroppedLibraries(droppedURLs.libraryURLs)

        guard !droppedURLs.importURLs.isEmpty else { return }

        var targetParentId: String?
        if case .library(let doc) = viewMode {
            targetParentId = doc?.id
        }

        let targetLibrary = LibraryManager.shared.getLibrary(id: windowState.libraryId)
            ?? LibraryManager.shared.globalLibrary

        Task { @MainActor in
            isImporting = true
            importError = nil

            guard let library = targetLibrary else {
                isImporting = false
                importProgress = nil
                importError = "No library available for import."
                logger.error("Run file drop import failed: no target library")
                return
            }

            // Route root-level drops to Inbox — bare files at library root
            // are invisible in the sidebar since only folders appear there.
            if targetParentId == nil {
                targetParentId = library.documentStore.collections.first(where: {
                    $0.name == "Inbox" && $0.parentId == nil && $0.docType == .folder
                })?.id
            }

            do {
                _ = try await library.importService.importFiles(
                    droppedURLs.importURLs,
                    mode: .copy,
                    parentId: targetParentId
                ) { current, total in
                    importProgress = "Importing \(current) of \(total)..."
                }
                await library.documentStore.refresh()
                logger.info("Successfully imported \(droppedURLs.importURLs.count) dropped item(s)")
            } catch {
                logger.error("Failed dropped import: \(String(describing: error))")
                importError = "Import failed: \(error.localizedDescription)"
            }

            if let importError {
                logger.error("Dropped import ended with error: \(importError)")
            }

            await MainActor.run {
                isImporting = false
                importProgress = nil
            }
        }
    }

    private func classifyDroppedURLs(_ urls: [URL]) -> (libraryURLs: [URL], importURLs: [URL]) {
        var libraryURLs: [URL] = []
        var importURLs: [URL] = []

        for url in urls {
            if url.isFicheroLibraryPackage {
                libraryURLs.append(url.standardizedFileURL)
            } else {
                importURLs.append(url)
            }
        }

        return (libraryURLs, importURLs)
    }

    private func openDroppedLibraries(_ urls: [URL]) {
        for libraryURL in urls {
            LibraryWindowOpener.openOrFocusLibrary(at: libraryURL, using: openWindow)
        }
    }
}

// MARK: - Helper Extension

private extension URL {
    var isFicheroLibraryPackage: Bool {
        guard pathExtension.localizedCaseInsensitiveCompare("fichero") == .orderedSame else {
            return false
        }

        let resourceValues = try? resourceValues(forKeys: [.contentTypeKey, .isDirectoryKey])
        if let contentType = resourceValues?.contentType,
           contentType.conforms(to: .ficheroSession) {
            return true
        }

        return resourceValues?.isDirectory == true
    }
}

// MARK: - Chat & Router Helpers

enum ChatScopeBuilder {
    static func currentScopeDocumentIds(
        browserSelection: Set<String>,
        currentDocuments: [Document],
        detailDocument: Document?
    ) -> [String] {
        let selectedIds = currentDocuments
            .filter { browserSelection.contains($0.id) && $0.docType != .folder }
            .map(\.id)
        if !selectedIds.isEmpty {
            return selectedIds
        }

        if let detailDocument, detailDocument.docType != .folder {
            return [detailDocument.id]
        }

        return currentDocuments
            .filter { $0.docType != .folder }
            .map(\.id)
    }
}

/// Where a toolbar search submit lands.
///
/// Deliberately carries no `SavedSearch`: a search is a transient view of the
/// library, not a stored object (#4086).
struct ToolbarSearchRoute: Equatable {
    let sidebarMode: SidebarMode
    let viewMode: AppViewMode
    /// The trimmed query the transient search runs (#4106/S2).
    let query: String
}

enum ToolbarSearchRouter {
    /// Returns the route for `rawQuery`, or nil when the query is blank.
    ///
    /// Search stays IN the library (#4106/S2): the sidebar keeps the library
    /// tree and the view mode keeps the Library view — only the library
    /// column's contents change, to the transient result set for `query`.
    static func route(for rawQuery: String) -> ToolbarSearchRoute? {
        let query = rawQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return nil }
        return ToolbarSearchRoute(
            sidebarMode: .library,
            viewMode: .library(nil),
            query: query
        )
    }
}

struct ChatWithDocsRoute: Equatable {
    let selectedDocumentIds: Set<String>
    let sidebarMode: SidebarMode
    let viewMode: AppViewMode
}

enum ChatWithDocsRouter {
    static func mainChatRoute(documentIds: [String]) -> ChatWithDocsRoute {
        ChatWithDocsRoute(
            selectedDocumentIds: Set(documentIds),
            sidebarMode: .chat,
            viewMode: .chat(nil)
        )
    }
}
