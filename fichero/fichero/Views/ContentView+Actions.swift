import OSLog
import SwiftUI
import UniformTypeIdentifiers
// swiftlint:disable file_length

// MARK: - ContentView Actions Extension
// Agent: ActionsAgent
// Responsibility: All action handlers, event handlers, and business logic methods

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ContentView")

// MARK: - Notification Names

extension Notification.Name {
    /// Posted when a page should be scrolled to in the PDF view
    static let scrollToPage = Notification.Name("scrollToPage")
}

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

extension ContentView {

    // MARK: - Document and Navigation Helpers

    /// Select a document by ID
    func selectDocument(withId documentId: String) {
        guard let doc = documentStore.currentDocuments.first(where: { $0.id == documentId }) else { return }
        // Image prev/next (and any other id-based navigation) flows through
        // here. If a Page Content editor has an in-flight edit, persist it via
        // the store-owned save BEFORE the focused document changes, otherwise
        // the edit is discarded when the editor reseeds to the new doc (#2476).
        // Only defer when an editor is actually registered so ordinary
        // selection stays synchronous.
        if documentStore.activePageEditFlush != nil {
            Task { @MainActor in
                await documentStore.flushActivePageEdit()
                detailDocument = doc
                browserSelection = [documentId]
            }
        } else {
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
        // Only offer the preview pane to Tab-cycling when one actually renders.
        // In widescreen both the canvas and reading panes can be hidden (#1448),
        // in which case focusing .preview would be a no-op (#1516).
        let previewPaneVisible = currentLayoutMode != .widescreen
            || showDocumentCanvas || showReadingPane
        if showsPreviewPane && previewPaneVisible {
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
            if isEntityLibrarySelection {
                return false
            }
            // Stable layout (default): a folder keeps the same panes as a file,
            // so selecting different items never reflows the window (#1452). The
            // legacy behaviour — folder collapses the preview so the grid takes
            // full width (#712) — is now opt-in via layoutFollowsSelection.
            if layoutFollowsSelection, let doc = inspectorDocument, doc.docType == .folder {
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
            sidebarSelectionState.selectedItemId = "doc:\(collection.id)"

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
        if horizontalSizeClass == .compact || shouldUseRuntimeSidebarCollapse {
            return
        }
        withAnimation {
            showSidebar.toggle()
            updateColumnVisibility()
        }
    }

    func handleWindowWidthChange(_ newWidth: Double) {
        guard newWidth > 0 else { return }
        if abs(measuredWindowWidth - newWidth) < 0.5 {
            return
        }
        measuredWindowWidth = newWidth
        updateColumnVisibility()
    }

    func updateColumnVisibility() {
        if horizontalSizeClass == .compact {
            return
        }
        // No animation — instant sidebar show/hide (#2309).
        if shouldUseRuntimeSidebarCollapse {
            columnVisibility = .detailOnly
        } else {
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

                sidebarSelectionState.selectedItemId = "search:\(saved.id)"
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

        viewSettings.libraryLayout = effectiveMode.libraryLayout
        saveDisplayMode(effectiveMode, for: sidebarSelectionState.selectedItemId)
        // Promote to the global default so a fresh window / new folder
        // / new launch all start in this mode. Per-folder overrides
        // (saveDisplayMode above) still win when present. (#943)
        defaultLibraryViewDisplayMode = effectiveMode
    }

    func updateLayoutMode(_ requestedMode: LayoutMode) {
        guard availableLayoutModes.contains(requestedMode) else { return }

        let previewMode: PreviewMode = switch requestedMode {
        case .none: .none
        case .standard: .standard
        case .widescreen: .widescreen
        }

        viewSettings.previewMode = normalizedPreviewMode(previewMode)
        currentLayoutMode = requestedMode

        // Legacy-recovery net: a window persisted with all panes hidden (before
        // the #1696 invariant existed) gets a pane back on entering widescreen.
        // The invariant makes all-hidden unreachable for new state.
        if requestedMode == .widescreen, !paneVisibility.isAnyVisible {
            setPaneVisible(.canvas, true)
        }
    }

    func setCanvasPaneVisible(_ isVisible: Bool) {
        if isVisible {
            currentLayoutMode = .widescreen
            viewSettings.previewMode = .widescreen
        }
        // Route through the invariant (#1696): hiding the last visible pane is
        // refused, so the content area is never left empty.
        setPaneVisible(.canvas, isVisible)
    }

    func setReadingPaneVisible(_ isVisible: Bool) {
        if isVisible {
            currentLayoutMode = .widescreen
            viewSettings.previewMode = .widescreen
        }
        setPaneVisible(.reading, isVisible)
    }

    func openChatWithCurrentScope() {
        // Follow-up (#1723): keep this discoverable sidebar entry, but promote the
        // scoped-docs chat into a first-class inspector pane/tab once the
        // library inspector gets a stable chat slot.
        let scopedIds = ChatScopeBuilder.currentScopeDocumentIds(
            browserSelection: browserSelection,
            currentDocuments: documentStore.currentDocuments,
            detailDocument: detailDocument
        )
        let route = ChatWithDocsRouter.mainChatRoute(documentIds: scopedIds)
        chatSelectedDocuments = route.selectedDocumentIds
        sidebarMode = route.sidebarMode
        viewMode = route.viewMode
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

    // MARK: - Sibling Document Navigation (#593 / #2420)

    /// Returns the sibling set used for prev/next navigation. When the current
    /// document is an image or page, navigation is scoped to image/page siblings
    /// only; otherwise all folder siblings are navigable.
    private func navigableSiblings(for document: Document) -> [Document] {
        navigableFolderSiblings(for: document, in: documentStore.currentDocuments)
    }

    /// Move detailDocument + browserSelection to the previous sibling in the
    /// current folder's sort order. Wraps with a small easeInOut animation so
    /// the EditorView's `.transition(.opacity)` produces a crossfade instead
    /// of a hard cut.
    func navigateSiblingPrevious() {
        guard let current = detailDocument else { return }
        let docs = navigableSiblings(for: current)
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
        let docs = navigableSiblings(for: current)
        guard let idx = docs.firstIndex(where: { $0.id == current.id }), idx < docs.count - 1 else { return }
        let target = docs[idx + 1]
        withAnimation(.easeInOut(duration: 0.2)) {
            detailDocument = target
            browserSelection = [target.id]
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

/// Returns the sibling set used for prev/next navigation. When `document` is an
/// image or page, navigation is scoped to image/page siblings only; otherwise all
/// folder siblings are navigable. Extracted so the filtering rule is unit-testable.
func navigableFolderSiblings(for document: Document, in documents: [Document]) -> [Document] {
    if document.fileType == .image || document.docType == .page {
        return documents.filter { $0.fileType == .image || $0.docType == .page }
    }
    return documents
}
