import SwiftUI

// MARK: - Source Highlight

extension PageContentPane {

    /// A `.readerTextSelection` post — a search hit's matched passage, a
    /// claim source, or a linked region — arrived.
    ///
    /// The anchor is LATCHED before it is applied (Daniel, 2026-09-03). This
    /// used to match-or-drop, which lost every anchor that arrived before the
    /// pane had the document's text: the post rides `detailDocument`
    /// changing, and the transcript is fetched after. Keeping the value means
    /// the landing happens when the text turns up, rather than not at all.
    func updateSourceHighlight(_ note: Notification) {
        // Only a post that ASKS the reader to land is a landing. The reader
        // publishes its own selection on this same seam (`postReaderSelection`,
        // for the preview's word boxes), and answering that would swap the
        // selectable text view for the static highlighted rendering under the
        // very drag that made the selection.
        guard ReaderPassageAnchor.isPassageLanding(note.userInfo),
              let anchor = ReaderPassageAnchor(userInfo: note.userInfo) else { return }
        pendingPassageAnchor = anchor
        applyPendingPassageAnchor()
    }

    /// Applies the latched anchor if it belongs to the document on screen and
    /// its text has loaded. Keeps the anchor on failure — the usual reason to
    /// fail is "not yet", and the re-application points (content arrival,
    /// document change, appear) are exactly where "not yet" becomes "now".
    func applyPendingPassageAnchor() {
        guard let doc = pageDoc, let anchor = pendingPassageAnchor,
              anchor.documentId == doc.id, !pageContent.isEmpty else { return }
        guard let highlight = PageContentClaimSourceHighlight.match(
            content: pageContent,
            documentId: doc.id,
            info: anchor.highlightInfo
        ) else { return }
        sourceHighlight = highlight
        sourceHighlightToken = UUID()
        pendingPassageAnchor = nil
        ReaderPassageFocus.consume(documentId: doc.id)
    }

    /// Picks up an anchor posted BEFORE this pane existed. Selecting a search
    /// result creates the reader and posts the anchor in the same turn, so a
    /// pane that only subscribed would have missed the very post it was
    /// subscribing for.
    func adoptLatestPassageAnchor() {
        guard let anchor = ReaderPassageFocus.latest,
              anchor.documentId == pageDoc?.id else { return }
        pendingPassageAnchor = anchor
        applyPendingPassageAnchor()
    }

    func syncSourceHighlightFromClaimFocus() {
        guard let doc = pageDoc else {
            sourceHighlight = nil
            return
        }
        let info: [AnyHashable: Any] = [
            "documentId": claimFocusState.selectedClaimSourceDocumentId as Any,
            "claimText": claimFocusState.selectedClaimText as Any,
            "charStart": claimFocusState.selectedClaimCharStart as Any,
            "charEnd": claimFocusState.selectedClaimCharEnd as Any
        ]
        guard let highlight = PageContentClaimSourceHighlight.match(
            content: pageContent,
            documentId: doc.id,
            info: info
        ) else {
            sourceHighlight = nil
            return
        }
        sourceHighlight = highlight
        sourceHighlightToken = UUID()
    }
}
