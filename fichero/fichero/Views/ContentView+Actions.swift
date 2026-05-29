import OSLog
import SwiftUI

// MARK: - ContentView Actions Extension
// Agent: ActionsAgent
// Responsibility: All action handlers, event handlers, and business logic methods

private let logger = Logger(subsystem: "com.fichero.fichero", category: "ContentView")

// MARK: - Notification Names

extension Notification.Name {
    /// Posted when a page should be scrolled to in the PDF view
    static let scrollToPage = Notification.Name("scrollToPage")
}

extension ContentView {

    // MARK: - Document and Navigation Helpers

    /// Select a document by ID
    func selectDocument(withId documentId: String) {
        if let doc = documentStore.currentDocuments.first(where: { $0.id == documentId }) {
            detailDocument = doc
            browserSelection = [documentId]
        }
    }

    /// Scroll to a specific page in the PDF
    private func scrollToPage(pageLabel: String) {
        // This will be implemented in the PDFPageView component
        // For now, we'll post a notification that the PDF view can listen to
        NotificationCenter.default.post(
            name: .scrollToPage,
            object: self,
            userInfo: ["pageLabel": pageLabel]
        )
    }

    // MARK: - Pane Focus Cycling

    /// Cycle keyboard focus between sidebar, content, and inspector panes
    func cyclePaneFocus(reverse: Bool) {
        var panes: [PaneFocus] = [.sidebar, .content]
        if showsPreviewPane {
            panes.append(.preview)
        }
        if showInspectorSidebar {
            panes.append(.inspector)
        }

        guard let current = focusedPane, let idx = panes.firstIndex(of: current) else {
            // No pane focused — default to content
            focusedPane = .content
            return
        }

        if reverse {
            focusedPane = panes[(idx - 1 + panes.count) % panes.count]
        } else {
            focusedPane = panes[(idx + 1) % panes.count]
        }
    }

    // MARK: - Claim Selection Sync

    /// Handle claim selection from any pane and sync to all other panes
    func syncClaimSelection(
        claimId: String,
        claimText: String? = nil,
        sourceDocumentId: String? = nil,
        pageLabel: String? = nil,
        charStart: Int? = nil,
        charEnd: Int? = nil
    ) {
        // Only sync if the feature is enabled
        guard FeatureManager.shared.isClaimHighlightSyncEnabled else { return }

        logger.debug("Syncing claim selection: \(claimId)")

        // Update the global claim focus state
        claimFocusState.selectClaim(
            claimId: claimId,
            claimText: claimText,
            sourceDocumentId: sourceDocumentId,
            pageLabel: pageLabel,
            charStart: charStart,
            charEnd: charEnd
        )

        // If the claim has a source document, select it in the grid
        if let sourceDocId = sourceDocumentId, sourceDocId != inspectorDocument?.id {
            selectDocument(withId: sourceDocId)
        }

        // If the claim has page information, scroll to it in the PDF
        if let pageLabel = pageLabel {
            scrollToPage(pageLabel: pageLabel)
        }
    }

    /// Clear the claim selection
    func clearClaimSelection() {
        guard FeatureManager.shared.isClaimHighlightSyncEnabled else { return }
        claimFocusState.clearSelection()
    }

    func handleKGFocusChanged() {
        guard let sourceDocId = kgFocusState.sourceDocumentId,
              !sourceDocId.isEmpty else { return }
        Task { @MainActor in
            await focusKGSourcePreview(sourceDocId)
            var info: [String: Any] = ["documentId": sourceDocId]
            if let claimId = kgFocusState.focusedClaimId, !claimId.isEmpty {
                info["claimId"] = claimId
            }
            if let pageLabel = kgFocusState.sourcePageLabel, !pageLabel.isEmpty {
                info["pageLabel"] = pageLabel
            }
            NotificationCenter.default.post(
                name: .ficheroNavigateToPage,
                object: nil,
                userInfo: info
            )
        }
    }

    var showsPreviewPane: Bool {
        guard currentLayoutMode != .none else { return false }
        switch viewMode {
        case .library:
            // Hide preview pane when a folder is selected — grid takes
            // full width, inspector shows folder metadata. (#712)
            if let doc = inspectorDocument, doc.docType == .folder {
                return false
            }
            return true
        case .search:
            return true
        default:
            return false
        }
    }

    // MARK: - Document Change Handler

    @MainActor
    func handleDocumentChange(_ change: DocumentChange) {
        switch change {
        case .collectionsUpdated:
            break

        case .collectionSelected(let collection):
            selectedSidebarItemId = "doc:\(collection.id)"

        case .documentsUpdated:
            break

        case .documentDeleted(let document):
            browserSelection.remove(document.id)
            if detailDocument?.id == document.id {
                detailDocument = nil
            }

        case .documentCreated:
            break
        }
    }

    // MARK: - UI Actions

    func toggleSidebar() {
        withAnimation {
            showSidebar.toggle()
            updateColumnVisibility()
        }
    }

    func updateColumnVisibility() {
        withAnimation {
            // 2-column layout: sidebar + detail (inspector is a panel inside detail).
            columnVisibility = showSidebar ? .all : .detailOnly
        }
    }

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

    func runToolbarSearch(_ rawQuery: String) {
        guard featureManager.isSearchEnabled else { return }
        let query = rawQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return }

        Task { @MainActor in
            do {
                let saved = try await savedSearchService.saveSearch(
                    query: query,
                    isSmartSearch: true,
                    searchType: "hybrid",
                    sortBy: "relevance",
                    sortDirection: "desc"
                )
                try await savedSearchService.loadSavedSearches()

                let search = SavedSearch(
                    id: saved.id,
                    name: saved.query,
                    query: saved.query,
                    isSmartSearch: saved.isSmartSearch,
                    folderPath: saved.folderPath,
                    sortOrder: saved.sortOrder
                )

                selectedSidebarItemId = "search:\(saved.id)"
                sidebarMode = .search
                viewMode = .search(search)
            } catch {
                logger.error("Toolbar search failed: \(error.localizedDescription)")
            }
        }
    }

    func updateViewDisplayMode(_ requestedMode: ViewDisplayMode) {
        let effectiveMode = normalizedViewDisplayMode(requestedMode)
        if effectiveMode != viewDisplayMode {
            viewDisplayMode = effectiveMode
        }

        viewSettings.libraryLayout = switch effectiveMode {
        case .icon: .icons
        case .list: .list
        case .table: .table
        case .map: .map
        }
        saveDisplayMode(effectiveMode, for: selectedSidebarItemId)
        // Promote to the global default so a fresh window / new folder
        // / new launch all start in this mode. Per-folder overrides
        // (saveDisplayMode above) still win when present. (#943)
        defaultLibraryViewDisplayMode = effectiveMode
    }

    // MARK: - File Import

    func handleFileDrop(urls: [URL]) {
        logger.info("Files dropped: \(urls.map { $0.lastPathComponent })")

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
                    urls,
                    mode: .copy,
                    parentId: targetParentId
                ) { current, total in
                    importProgress = "Importing \(current) of \(total)..."
                }
                await library.documentStore.refresh()
                logger.info("Successfully imported \(urls.count) dropped item(s)")
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

    // MARK: - Sibling Document Navigation (#593)

    /// Move detailDocument + browserSelection to the previous sibling in the
    /// current folder's sort order. Wraps with a small easeInOut animation so
    /// the EditorView's `.transition(.opacity)` produces a crossfade instead
    /// of a hard cut.
    func navigateSiblingPrevious() {
        guard let current = detailDocument else { return }
        let docs = documentStore.currentDocuments
        guard let idx = docs.firstIndex(where: { $0.id == current.id }), idx > 0 else { return }
        let target = docs[idx - 1]
        withAnimation(.easeInOut(duration: 0.2)) {
            detailDocument = target
            browserSelection = [target.id]
        }
    }

    /// Move to the next sibling. Symmetric to navigateSiblingPrevious.
    func navigateSiblingNext() {
        guard let current = detailDocument else { return }
        let docs = documentStore.currentDocuments
        guard let idx = docs.firstIndex(where: { $0.id == current.id }), idx < docs.count - 1 else { return }
        let target = docs[idx + 1]
        withAnimation(.easeInOut(duration: 0.2)) {
            detailDocument = target
            browserSelection = [target.id]
        }
    }
}
