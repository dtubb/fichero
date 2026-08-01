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

        // Capture the browsed folder BEFORE clearing the selection so the
        // results bar can offer it as a scope (#4107/S3).
        if case .library(let doc) = viewMode, let doc, doc.docType == .folder {
            transientSearchContextFolder = TransientSearchFolder(id: doc.id, name: doc.name)
        } else {
            transientSearchContextFolder = nil
        }
        // Finder-style default scope (#4108/S4); folder scope only applies
        // when there IS a browsed folder to scope to.
        transientSearchScopeIsFolder = transientSearchContextFolder != nil
            && UserDefaults.standard.bool(forKey: Self.searchDefaultScopeIsFolderKey)
        sidebarSelectionState.selectedItemId = nil
        sidebarMode = route.sidebarMode
        viewMode = route.viewMode
        activeSearchQuery = route.query
        transientSearchLimit = Self.transientSearchPageSize
        Task { @MainActor in
            // Explicit submit → in Ask mode (#4117) the LLM may compile a
            // sentence-like query into a structured search (#4116); Keyword
            // mode searches the raw text (the engine's natural-language gate
            // also skips keyword-looking queries in Ask mode).
            await runTransientSearch(route.query, compile: searchFieldMode == .ask)
        }
    }

    // MARK: - File Import

    /// The content-pane's NSItemProvider path (#4458) — resolves providers
    /// via the SAME `ExternalFileDropLoader` the sidebar row drop target
    /// uses (#4184: one loader, not two), then hands the resolved URLs to
    /// the SAME `handleFileDrop` the Finder-drag `.dropDestination` path
    /// already calls. This is the supplementary path for content-UTI-only
    /// providers (Mail attachments, Safari image/PDF drags, in-progress
    /// Downloads) that `.dropDestination(for: URL.self)` misses — it does
    /// not replace that path, which stays the proven-safe route for the
    /// common Finder-drag case.
    func handleContentPaneExternalDrop(_ providers: [NSItemProvider]) {
        Task {
            var urls: [URL] = []
            for provider in providers {
                if let url = try? await ExternalFileDropLoader.loadAnyFileURL(from: provider) {
                    urls.append(url)
                }
            }
            guard !urls.isEmpty else {
                logger.warning("Content-pane drop: all provider loads failed — import won't fire")
                await MainActor.run {
                    importError = "Couldn't read the dropped item(s). Nothing was imported."
                }
                return
            }
            await MainActor.run {
                handleFileDrop(urls: urls)
            }
        }
    }

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

            let batches = Self.contentDropBatches(
                urls: droppedURLs.importURLs,
                browsedFolderId: targetParentId,
                inboxId: library.documentStore.collections.first(where: {
                    $0.name == "Inbox" && $0.parentId == nil && $0.docType == .folder
                })?.id
            )

            do {
                for batch in batches {
                    _ = try await library.importService.importFiles(
                        batch.urls,
                        mode: .copy,
                        parentId: batch.parentId
                    ) { current, total in
                        importProgress = "Importing \(current) of \(total)..."
                    }
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

            // Already on the MainActor (Task { @MainActor } above).
            isImporting = false
            importProgress = nil
        }
    }

    /// Import batches for a content-pane drop. Browsing a folder targets it
    /// directly; a root-level drop splits per #4274 — FOLDERS import at the
    /// root itself (sidebar-visible there; the blanket Inbox redirect buried
    /// dropped folders where the user wasn't looking, reading as "didn't
    /// import"), bare files still route to Inbox (invisible at root).
    static func contentDropBatches(
        urls: [URL], browsedFolderId: String?, inboxId: String?
    ) -> [LibraryRootImportBatch] {
        if let browsedFolderId {
            return [LibraryRootImportBatch(parentId: browsedFolderId, urls: urls)]
        }
        return libraryRootImportBatches(
            urls: urls, inboxId: inboxId, isDirectory: libraryDropURLIsDirectory
        )
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
