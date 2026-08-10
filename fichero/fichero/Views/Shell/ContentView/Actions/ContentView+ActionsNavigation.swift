import OSLog
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
        NavTrace.log("selectDocument", "→ \(documentId)")
        if documentStore.activePageEditFlush != nil {
            Task { @MainActor in
                await documentStore.flushActivePageEdit()
                NavTrace.log("selectDocument.afterFlush", "→ \(documentId)")
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
        NavTrace.log("previewSiblingSwipe", "direction \(direction)")
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
        NavTrace.log("navigateSiblingPrevious", "\(current.id) → \(target.id)")
        withAnimation(.easeInOut(duration: 0.2)) {
            detailDocument = target
            browserSelection = [target.id]
        }
        prefetchAdjacentSiblingDisplays(around: idx - 1, in: docs)
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
        NavTrace.log("navigateSiblingNext", "\(current.id) → \(target.id)")
        withAnimation(.easeInOut(duration: 0.2)) {
            detailDocument = target
            browserSelection = [target.id]
        }
        prefetchAdjacentSiblingDisplays(around: idx + 1, in: docs)
    }

    /// ★ EVERY FRAME PERFECT: warm the display cache both directions around
    /// a sibling step, nearest first, so the NEXT swipe finds its image
    /// cached and swaps in place — the reader's #18 page-turn prefetch,
    /// extended to sibling navigation (Daniel, 2026-08-10: flips showed the
    /// old page, then reloaded). Best-effort; the pool skips cached ids.
    private func prefetchAdjacentSiblingDisplays(around index: Int, in docs: [Document]) {
        let neighborIds = [index + 1, index - 1, index + 2, index - 2]
            .filter { docs.indices.contains($0) }
            .map { docs[$0].id }
        guard !neighborIds.isEmpty else { return }
        let storage = storageService
        Task { await storage.prefetchDisplayImages(neighborIds) }
    }
}

// MARK: - Navigation write tracing (Debug diagnostic, 2026-08-10)
//
// Daniel's swipe/page-select bug shows a WRITE RACE ("shows the same page
// then changes"; "I select a page and it goes back to the first"). Every
// writer of detailDocument/browserSelection in the navigation family logs
// through here with a monotonically increasing sequence number, so ONE
// gesture in a live session prints the exact write order. Remove (or quiet)
// once the race is fixed.
enum NavTrace {
    nonisolated(unsafe) static var seq = 0
    static func log(_ site: String, _ detail: String) {
        #if DEBUG
        seq += 1
        navTraceLogger.info("NAVTRACE #\(seq) \(site): \(detail)")
        #endif
    }
}

private let navTraceLogger = Logger(subsystem: "app.fichero.fichero", category: "NavTrace")

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
