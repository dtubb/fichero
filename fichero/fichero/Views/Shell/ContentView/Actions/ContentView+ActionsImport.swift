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

        // #4521: search chrome is summoned, and a programmatic search (entity
        // lozenge, saved search) must summon it too — results with no visible
        // query field would look like an unexplained library.
        showSearchField = true

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
        // New query → relevance order until the user explicitly re-sorts (#11).
        libraryToolbarState.userChoseSortDuringSearch = false
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
        // Loads issued synchronously in the drop callback (drop#44 fix).
        let eager = eagerSidebarDropLoads(providers)
        Task {
            // Read the payload BEFORE resolving any file URL (#4401). `.item`
            // is UTType's root, so this destination matches every in-app drag
            // too — and since #4123 a document row exports a real file, which
            // the loader below would happily resolve and import. Dragging a
            // document from the sidebar into the content pane therefore made a
            // second, hollow copy of it. Positive identification first is the
            // same rule the sidebar row and the folder cell already follow.
            switch await readSidebarDropPayload(providers, surface: "content-pane", preloaded: eager) {
            case .internalItems, .unreadableInternal:
                // NO alert for a no-op internal drop (Daniel #133, 2026-08-09:
                // "nothing should happen, don't do an alert") — the drag
                // simply doesn't land; macOS snaps the item back. The refusal
                // is fully logged for diagnosis instead.
                logger.error("Content-pane drop came from inside the app; refusing to import (no-op, no alert)")
                return
            case .externalFiles, .unsupported:
                break
            }
            var urls: [URL] = []
            for provider in providers {
                if let url = try? await ExternalFileDropLoader.loadAnyFileURL(from: provider) {
                    urls.append(url)
                }
            }
            guard !urls.isEmpty else {
                // Unreadable payloads stay silent too (Daniel #136: 'if drop
                // fails don't do alert, unless its obvious. but log it
                // properly') — nothing moved, nothing lost, snap-back says no.
                logger.error("Content-pane drop: all provider loads failed — import won't fire (no-op, no alert)")
                return
            }
            await MainActor.run {
                handleFileDrop(urls: urls)
            }
        }
    }

    /// Drop this app's OWN drag export before anything can import it (#4401),
    /// returning only the genuinely external URLs.
    ///
    /// This is the last line of defence and the only one available on the
    /// URL-typed route. `DropTargetModifiers` reaches `handleFileDrop` via
    /// `.dropDestination(for: URL.self)` mounted on the WHOLE
    /// `NavigationSplitView` — sidebar and detail both — and a Transferable
    /// destination typed on URL never sees the providers, so it cannot ask what
    /// the drag carried. What it CAN see is that the URL sits in the temp
    /// directory this app writes for its own drag export, which makes it a copy
    /// of a document already in the library. Importing that is the duplication
    /// the whole issue is about.
    private func externalURLsRefusingOwnDragExports(_ urls: [URL]) -> [URL] {
        let (external, internalExports) = partitionFicheroInternalDragExports(urls)
        guard !internalExports.isEmpty else { return external }
        // NO alert (Daniel #133): the internal-export portion is a no-op —
        // logged, dropped, and the genuinely external files still import.
        logger.error(
            "Refusing to import \(internalExports.count) item(s) dragged from inside the app (no-op, no alert)"
        )
        return external
    }

    /// Say so when a dropped link is refused, rather than letting the drop do
    /// nothing (#2386).
    ///
    /// Downloading a remote URL is a real feature with its own failure surface
    /// and is NOT built here. What is built here is honesty: a remote URL is
    /// recognised as remote and SAID SO, instead of being handed to the
    /// importer as a file path that does not exist.
    ///
    /// Lives on the view, not on `DroppedURLs`: it needs `importError` and the
    /// file's logger, and keeping them out of the value type is what lets
    /// `DroppedURLs.classify` be tested without a window.
    private func reportRefusedRemoteURLs(_ remoteURLs: [URL]) {
        guard !remoteURLs.isEmpty else { return }
        logger.warning("Refusing \(remoteURLs.count) remote URL(s): link import is not implemented")
        importError = """
            Importing from a web link isn't supported yet. \
            Download the file first, then drop it here.
            """
    }

    func handleFileDrop(urls: [URL]) {
        logger.info("Files dropped: \(urls.map { $0.lastPathComponent })")

        let external = externalURLsRefusingOwnDragExports(urls)
        guard !external.isEmpty else { return }

        let droppedURLs = DroppedURLs.classify(external)
        openDroppedLibraries(droppedURLs.libraryURLs)

        reportRefusedRemoteURLs(droppedURLs.remoteURLs)

        guard !droppedURLs.importURLs.isEmpty else { return }

        var targetParentId: String?
        if case .library(let doc) = viewMode {
            targetParentId = doc?.id
        }

        let targetLibrary = LibraryManager.shared.getLibrary(id: windowState.libraryId)
            ?? LibraryManager.shared.globalLibrary

        // #4459: sweep the `fichero-drop-UUID` directories this drop created.
        // `loadFileRepresentation` hands back a temp file that dies when its
        // callback returns, so `ExternalFileDropLoader` copies it somewhere
        // stable — and SOMEBODY has to delete that copy afterwards.
        //
        // The sidebar row already does exactly this (`SidebarItemRow+DropHandlers`
        // :110-119): collect the directories, `defer` their removal past the
        // import. The content pane never did, so every drop through the window
        // left a directory behind. Two paths, one obligation, and nothing
        // forcing the second to know about it.
        //
        // `defer` rather than a trailing call: the import has several early
        // returns (no library, empty batch, a throw) and a leak on the failure
        // path is the one most likely to go unnoticed.
        let temporaryDirectories = externalDropTemporaryDirectories(for: droppedURLs.importURLs)

        Task { @MainActor in
            defer { DroppedURLs.removeTemporaryDirectories(temporaryDirectories) }
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
                let outcome = try await importDropBatches(batches, into: library)
                await library.documentStore.refresh()
                // #3276: `importFiles` throws only when EVERY file in a batch
                // failed, so without this a drop that lost some files logged
                // "Successfully imported N" and raised no alert.
                if let message = outcome.partialFailureMessage {
                    importError = message
                } else {
                    logger.info("Successfully imported \(droppedURLs.importURLs.count) dropped item(s)")
                }
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

    /// Run every batch of a content-pane drop and MERGE what they achieved
    /// (#3276). One drop is one gesture and deserves one verdict: reporting per
    /// batch would either raise two banners for one drop, or let a clean second
    /// batch overwrite the first batch's failure — the same silence in a
    /// different shape.
    @MainActor
    private func importDropBatches(
        _ batches: [LibraryRootImportBatch],
        into library: LibraryManager.LibraryReference
    ) async throws -> ImportOutcome {
        var outcomes: [ImportOutcome] = []
        for batch in batches {
            outcomes.append(try await library.importService.importFiles(
                batch.urls,
                mode: .copy,
                parentId: batch.parentId
            ) { current, total in
                importProgress = "Importing \(current) of \(total)..."
            })
        }
        return ImportOutcome.merged(outcomes)
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

    private func openDroppedLibraries(_ urls: [URL]) {
        for libraryURL in urls {
            LibraryWindowOpener.openOrFocusLibrary(at: libraryURL, using: openWindow)
        }
    }
}

// MARK: - Helper Extension

// `internal`, not `private`: `DroppedURLs.classify` is a pure static in its own
// file and cannot see a file-scoped helper. Swift's `private` is FILE-scoped, so
// splitting the classifier out took this away from it — which `swiftc -parse`
// does not catch, only a real build does.
extension URL {
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
