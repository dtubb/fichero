import OSLog
import SwiftUI

// MARK: - Reading Layout Helpers (#1189)
//
// PDF page-index math + grid↔page sync used by the reader. The old
// `fivePaneReadingView` (page-strip | PDF | content) was retired in the reader
// IA fold — its role is now the tabbed reader's Page tab.

extension ContentView {

    /// Sync grid selection to the PDF page at `index`. Fired from
    /// PDFPageView's coordinator when the user scrolls to a different page
    /// in multi-page mode (#586). Finds the matching page Document among
    /// `documentStore.currentDocuments` and updates `detailDocument`.
    ///
    /// The `sequence - 1 == index` formula converts our 1-based `sequence`
    /// (page_number) to PDFKit's 0-based index.
    /// Pure: the page Document whose 1-based `sequence` maps to PDFKit's 0-based
    /// `index` (`sequence - 1 == index`). Extracted for #3013 page-index tests.
    static func pageDocument(atPDFIndex index: Int, in documents: [Document]) -> Document? {
        documents.first { $0.docType == .page && ($0.sequence ?? 0) == index + 1 }
    }

    /// Pure: the page children a reader page signal may resolve against.
    ///
    /// The reader's page children are NOT reliably in `currentDocuments`:
    /// `currentDocuments` holds the children of the *browsed container*, so
    /// when the selection is the folder that contains the PDF (the ordinary
    /// way a PDF gets opened) the page children live only in `childrenCache`
    /// — the same split #4357 already handles for per-page run progress.
    /// Resolving a click against `currentDocuments` alone made every reader
    /// page click fail with "found no page document" whenever the library
    /// selection was the parent folder rather than the PDF itself.
    ///
    /// Candidates are scoped to the reader document's own page parent, so a
    /// window browsing one container while reading another can never resolve
    /// a click to a page of some *other* document that happens to share a
    /// sequence number. With no reader document there is nothing to scope by,
    /// so the legacy behavior (search the browsed container) is kept.
    static func readerPageCandidates(
        readerDocument: Document?,
        childrenCache: [String: [Document]],
        currentDocuments: [Document]
    ) -> [Document] {
        guard let doc = readerDocument else { return currentDocuments }
        let parentId = (doc.docType == .page ? doc.parentId : doc.id) ?? doc.id
        let cached = childrenCache[parentId] ?? []
        let browsed = currentDocuments.filter { $0.parentId == parentId }
        var seen = Set<String>()
        return (cached + browsed).filter { seen.insert($0.id).inserted }
    }

    /// Pure: page-document ids at pdfIndex ±1/±2 — the prefetch set for a
    /// page turn (#18). Nearest neighbours first so the bounded prefetch pool
    /// warms the likeliest next flip before the speculative ones.
    static func adjacentPageIds(around pageIndex: Int, in candidates: [Document]) -> [String] {
        [-1, 1, -2, 2].compactMap { offset in
            let index = pageIndex + offset
            guard index >= 0 else { return nil }
            return Self.pageDocument(atPDFIndex: index, in: candidates)?.id
        }
    }

    /// Pure: the 0-based PDF page index for a page Document (1-based `sequence`),
    /// clamped to 0; non-page docs (or nil) resolve to the first page. (#3013)
    static func pdfPageIndex(for doc: Document?) -> Int {
        guard let doc, doc.docType == .page else { return 0 }
        return max(0, (doc.sequence ?? 1) - 1)
    }

    /// The reader scrolled past a page. Moves the page-focus cursor only —
    /// never `detailDocument`, never `browserSelection` (#1463).
    func syncGridSelectionToPDFPage(index: Int) {
        applyReaderPageSignal(.scrolledPast, pageIndex: index)
    }

    /// The user CLICKED a page in the reader (#4373).
    ///
    /// Routes through the same page resolution and the same state the scroll
    /// path uses — one selection seam, not a parallel navigation — and then
    /// applies the one extra thing a click is allowed to do: move the library
    /// selection. The preview and inspector follow `pageFocusDocument` as they
    /// already do, so no extra wiring is needed for either.
    func handleReaderPageActivated() {
        guard let request = readerPageActivationState.currentRequest else { return }
        applyReaderPageSignal(.clicked, pageIndex: request.pageIndex)
    }

    /// The one place a reader page signal is applied. `signal` decides how much
    /// of the window may move; everything else is identical between the two.
    ///
    /// EDITS FIRST (Daniel 2026-08-09, live: "the content window always needs
    /// to save if I've made changes" — a swipe reseeded the Content editor
    /// from the NEW page and the draft was replaced unsaved). The in-flight
    /// page-content edit flushes BEFORE the page focus moves; a clean editor
    /// makes this a guarded no-op, so ordinary swipes pay nothing.
    private func applyReaderPageSignal(_ signal: ReaderPageSignal, pageIndex: Int) {
        // SYNCHRONOUS when there is nothing to flush (2026-08-11, the
        // snap-back race): the Task hop deferred the state write by a runloop
        // turn even for a clean editor, so PDFKit had already flipped while
        // the parent still rendered the OLD selectedPageIndex — and the
        // pane's keep-in-step onChange pushed the stale page back. Only an
        // actual in-flight edit pays the async flush.
        guard documentStore.activePageEditFlush != nil else {
            applyReaderPageSignalAfterFlush(signal, pageIndex: pageIndex)
            return
        }
        Task { @MainActor in
            await documentStore.flushActivePageEdit()
            applyReaderPageSignalAfterFlush(signal, pageIndex: pageIndex)
        }
    }

    /// The signal resolved to no page DOCUMENT. The reader must PAGE even when
    /// the pages are not imported as documents (Daniel, 2026-08-09: a 21-page
    /// PDF selected from the grid — "you ought to be able to change pages even
    /// though it can't update the position"). Returning without moving the
    /// cursor left the parent's selectedPageIndex unchanged, and the pane's
    /// keep-in-step onChange snapped the view straight back. A VIRTUAL page
    /// cursor keeps the reader's place; it is marked and never enters
    /// browserSelection.
    private func applyUnresolvedReaderPageSignal(
        _ signal: ReaderPageSignal, pageIndex: Int, candidates: [Document]
    ) {
        if signal.movesPageFocus, let pdfId = detailPDFDocumentId {
            // Instrumented (2026-08-11): this branch was the ONE page-focus
            // writer without a trace — the reason swipe repros printed
            // vpage artifact fetches but zero NAVTRACE lines.
            NavTrace.log("readerPageActivation.virtualPage", "\(pdfId) → page \(pageIndex)")
            pageFocusDocument = Document.virtualPageCursor(pdfParentId: pdfId, pageIndex: pageIndex)
        }
        // Routine while scrolling — the transcript can report a page before
        // its children have loaded — but a CLICK that resolves to nothing
        // deserves a report. Which report depends on what actually
        // happened: a document with page children where the index missed
        // is a real resolution failure (the click "did nothing"); a
        // document with NO page children anywhere (single-page imports,
        // transcripts of unpaginated documents) has nothing to select, and
        // calling that an error was the #4373 over-logging Daniel saw.
        guard signal == .clicked else { return }
        let pageChildCount = Self.pdfDocPageCount(in: candidates)
        if pageChildCount > 0 {
            readerPageActivationLogger.error(
                """
                Reader page click found no page document at index \
                \(pageIndex, privacy: .public) among \
                \(pageChildCount, privacy: .public) page children
                """
            )
        } else {
            readerPageActivationLogger.debug(
                "Reader page click on a document with no page children — nothing to select"
            )
        }
    }

    private func applyReaderPageSignalAfterFlush(_ signal: ReaderPageSignal, pageIndex: Int) {
        let candidates = Self.readerPageCandidates(
            readerDocument: detailDocument ?? pageFocusDocument,
            childrenCache: documentStore.childrenCache,
            currentDocuments: documentStore.currentDocuments
        )
        guard let match = Self.pageDocument(atPDFIndex: pageIndex, in: candidates) else {
            applyUnresolvedReaderPageSignal(signal, pageIndex: pageIndex, candidates: candidates)
            return
        }
        if signal.movesPageFocus, pageFocusDocument?.id != match.id {
            NavTrace.log("readerPageActivation.pageFocus", "→ \(match.id)"); pageFocusDocument = match
        }
        // ★ EVERY FRAME PERFECT (#18): warm the display cache for the pages
        // either side of this turn, so the NEXT flip finds its image cached
        // and swaps in place with no fetch window. Best-effort — the prefetch
        // pool skips cached ids and swallows errors.
        let neighborIds = Self.adjacentPageIds(around: pageIndex, in: candidates)
        if !neighborIds.isEmpty {
            let storage = storageService
            Task { await storage.prefetchDisplayImages(neighborIds) }
        }
        // A page-turn now HIGHLIGHTS the page in the library and the sidebar
        // (Daniel, 2026-08-09: "swipe left and right, and then the page
        // changes in the sidebar"). A scroll/swipe never stomps a
        // multi-selection the user built — only a click replaces one.
        if signal.movesBrowserSelection,
           browserSelection != [match.id],
           signal == .clicked || browserSelection.count <= 1 {
            NavTrace.log("readerPageActivation.browserSelection", "→ \(match.id)"); browserSelection = [match.id]
            // Sidebar HIGHLIGHT only — a direct destinations write, never the
            // routing seam: routing would re-root the preview under the very
            // swipe that was meant to move within it (#1463 class). DEBOUNCED
            // (2026-08-09): a sidebar re-render per page-turn is a ~250ms
            // childrenList pass — the white-flash budget on fast swipes. The
            // highlight settles ~150ms after the last turn instead.
            let destination = SidebarDestination.document(match.id)
            if sidebarSelectionState.selectedDestinations != [destination] {
                sidebarHighlightDebounce?.cancel()
                sidebarHighlightDebounce = Task { @MainActor in
                    try? await Task.sleep(for: .milliseconds(150))
                    guard !Task.isCancelled else { return }
                    if sidebarSelectionState.selectedDestinations != [destination] {
                        sidebarSelectionState.selectedDestinations = [destination]
                    }
                }
            }
        }
        // `detailDocument` is deliberately untouched by BOTH signals: it is the
        // reader's own input, and re-rooting it reloads the WebKit transcript
        // under the click that was meant to move within it (#1463).
    }

    /// Resolved parent-PDF document id for the currently previewed document, or nil.
    var detailPDFDocumentId: String? {
        guard let doc = detailDocument else { return nil }
        guard CanvasDocumentPolicy.shouldUsePDFCanvas(for: doc) else { return nil }
        if doc.fileType == .pdf { return doc.id }
        if doc.docType == .page {
            return resolvedParentPDFDocumentId(for: doc)
        }
        return nil
    }

    /// Resolve the parent PDF document id for a page child. Page documents
    /// carry their own id, but the bytes live on the parent PDF document.
    func resolvedParentPDFDocumentId(for doc: Document) -> String? {
        let parentId = doc.metadata["pdf_parent_id"]?.value as? String ?? doc.parentId
        return parentId
    }

    /// Current PDF page index. Prefers pageFocusDocument (set by scroll/flip)
    /// over detailDocument so the PDF viewer tracks scrolling without
    /// re-rooting the active container (#1463).
    var selectedPageIndex: Int {
        Self.pdfPageIndex(for: pageFocusDocument ?? detailDocument)
    }

    /// Number of page-child documents for the previewed PDF (#3866). The reading
    /// pane needs only the COUNT, so this skips the O(n log n) filter+sort +
    /// array allocation that the old `pdfDocPages` accessor cost — read twice per
    /// render for `isEmpty ? nil : count`.
    var pdfDocPageCount: Int {
        Self.pdfDocPageCount(in: documentStore.currentDocuments)
    }

    /// Pure page-child count over a document set — no sort, no allocation
    /// (`lazy`). Static so it's unit-testable without a ContentView. (#3866)
    static func pdfDocPageCount(in documents: [Document]) -> Int {
        documents.lazy.filter { $0.docType == .page }.count
    }

}
