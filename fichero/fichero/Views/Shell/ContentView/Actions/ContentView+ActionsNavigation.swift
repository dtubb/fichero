import SwiftUI

// MARK: - ContentView Navigation Actions

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
    func scrollToPage(pageLabel: String) {
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
        // Daniel's order (2026-08-10): sidebar → library → preview →
        // reader → inspector — left to right, exactly as the panes sit in
        // the window. Only panes that actually RENDER join the cycle
        // (#1448/#1516: focusing a hidden pane is a no-op).
        var panes: [PaneFocus] = [.sidebar, .content]
        let previewPaneVisible = currentLayoutMode != .widescreen
            || showDocumentCanvas
        if showsPreviewPane && previewPaneVisible {
            panes.append(.preview)
        }
        if currentLayoutMode == .widescreen && showReadingPane {
            panes.append(.reading)
        }
        if showInspectorSidebar {
            panes.append(.inspector)
        }

        // The HINT is the cycle's memory (Daniel, 2026-08-10: "we ought to
        // have a way to move between panes"): focusedPane is FocusState and
        // usually nil (only the sidebar has a .focused binding), so cycling
        // from it perpetually reset to .content instead of ADVANCING.
        guard let current = focusedPane ?? paneFocusHint,
              let idx = panes.firstIndex(of: current) else {
            focusedPane = .content
            paneFocusHint = .content
            return
        }

        let next = reverse
            ? panes[(idx - 1 + panes.count) % panes.count]
            : panes[(idx + 1) % panes.count]
        focusedPane = next
        paneFocusHint = next
    }

    // MARK: - Sibling Document Navigation (#593 / #2420)

    /// Trackpad swipe → sibling step (Daniel, 2026-08-10: "swipe left or
    /// right … should take you to the next one in the library; up or down no").
    /// Posted by SiblingSwipeScrollView only when the current image cannot pan
    /// horizontally, so a zoomed pan never turns the page.
    func handlePreviewSiblingSwipe(_ notification: Notification) {
        guard let direction = notification.object as? Int else { return }
        if direction > 0 { navigateSiblingNext() } else { navigateSiblingPrevious() }
    }

    /// Returns the sibling set used for prev/next navigation. When the current
    /// document is an image or page, navigation is scoped to image/page siblings
    /// only; otherwise all folder siblings are navigable.
    private func navigableSiblings(for document: Document) -> [Document] {
        // #25: browsing INSIDE a selected folder — the current document is one
        // of the folder's children, which the library listing (the folder's
        // own siblings) does not contain. Its cached siblings-within-the-folder
        // are the navigable set, so swipes keep stepping through the folder.
        let listing = documentStore.currentDocuments
        if !listing.contains(where: { $0.id == document.id }),
           let parentId = document.parentId,
           let folderKids = documentStore.childrenCache[parentId],
           folderKids.contains(where: { $0.id == document.id }) {
            return navigableFolderSiblings(for: document, in: folderKids)
        }
        return navigableFolderSiblings(for: document, in: listing)
    }

    /// #25 (Daniel): a selected folder previews like a PDF — its items are its
    /// "pages". Stepping from the folder itself descends into its children;
    /// `navigableSiblings` above then keeps later steps inside the folder.
    private func navigateIntoFolder(_ folder: Document, forward: Bool) {
        Task { @MainActor in
            let kids = await documentStore.children(of: folder.id)
                .filter { $0.docType != .folder }
            guard let target = forward ? kids.first : kids.last else { return }
            withAnimation(.easeInOut(duration: 0.2)) {
                detailDocument = target
                browserSelection = [target.id]
            }
        }
    }

    /// A folder with no previewable source of its own (image- or PDF-backed
    /// "folders" preview themselves and step through the LIBRARY, not inward).
    private func isPlainFolder(_ doc: Document) -> Bool {
        doc.docType == .folder && doc.fileType != .image && doc.fileType != .pdf
    }

    /// Move detailDocument + browserSelection to the previous sibling in the
    /// current folder's sort order. Wraps with a small easeInOut animation so
    /// the EditorView's `.transition(.opacity)` produces a crossfade instead
    /// of a hard cut.
    func navigateSiblingPrevious() {
        guard let current = detailDocument else { return }
        if isPlainFolder(current) {
            navigateIntoFolder(current, forward: false)
            return
        }
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
        if isPlainFolder(current) {
            navigateIntoFolder(current, forward: true)
            return
        }
        let docs = navigableSiblings(for: current)
        guard let idx = docs.firstIndex(where: { $0.id == current.id }), idx < docs.count - 1 else { return }
        let target = docs[idx + 1]
        withAnimation(.easeInOut(duration: 0.2)) {
            detailDocument = target
            browserSelection = [target.id]
        }
    }
}

// MARK: - Helper Functions

/// Returns the sibling set used for prev/next navigation. When `document` is an
/// image or page, navigation is scoped to image/page siblings only; otherwise all
/// folder siblings are navigable. Extracted so the filtering rule is unit-testable.
func navigableFolderSiblings(for document: Document, in documents: [Document]) -> [Document] {
    if document.fileType == .image || document.docType == .page {
        return documents.filter { $0.fileType == .image || $0.docType == .page }
    }
    return documents
}

// MARK: - Notification Names

extension Notification.Name {
    /// Posted when a page should be scrolled to in the PDF view
    static let scrollToPage = Notification.Name("scrollToPage")
}
