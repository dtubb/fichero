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
