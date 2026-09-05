import SwiftUI

// Following a statement lands the reader ON the sentence it was read from
// (#4666).
//
// Daniel, 2026-09-04, on the SVO browser: the statements "seem to not be
// applying". Part of that is the extraction, and part of it is this: a
// statement you cannot follow back to the manuscript is an assertion, not
// evidence. The claim already carries everything needed to land — source
// document, page label, character offsets, and the verbatim quote — and the
// reader already knows how to land on a passage, because 787b624c2 taught it
// for search results.
//
// What that commit did NOT do was route claims through the same seam. A
// claim's highlight rode `claimFocusState`, whose sync in
// `PageContentPane+SourceHighlight` is match-or-CLEAR and is only re-run when
// the focus changes — never when the page's text arrives. Following a claim
// changes the document, so the transcript lands after the request, and the
// highlight was cleared before it could ever match. The latch below is the
// fix search already has: record before the reveal, post after it, and let a
// reader that mounts a frame later read the anchor on appear.

extension ContentView {
    /// Latch the passage a claim points at, BEFORE the reveal navigates.
    ///
    /// A no-op when the claim carries neither a quote nor offsets: an anchor
    /// that cannot say where it lands would send the reader somewhere
    /// arbitrary, which is worse than not moving it.
    func recordClaimPassageAnchor(_ request: ClaimSourceNavigationRequest) {
        let passageText = request.claimText ?? ""
        guard !request.documentId.isEmpty,
              !passageText.isEmpty || request.charStart != nil
        else { return }
        ReaderPassageFocus.record(
            ReaderPassageAnchor(
                documentId: request.documentId,
                text: passageText,
                charStart: request.charStart,
                charEnd: request.charEnd
            )
        )
    }

    /// Announce the latched passage to the surfaces already on screen.
    ///
    /// `highlightInfo` is the ONE shape `PageContentClaimSourceHighlight.match`
    /// reads, so a claim source and a search passage can never disagree about
    /// offsets. The kind marker says "land here" rather than "here is a
    /// selection" — the reader publishes on this seam too, and must not answer
    /// its own post.
    func postClaimPassageAnchor(documentId: String) {
        guard let anchor = ReaderPassageFocus.latest,
              anchor.documentId == documentId else { return }
        var info = anchor.highlightInfo
        info["text"] = anchor.text
        info[ReaderPassageAnchor.kindKey] = ReaderPassageAnchor.searchPassageKind
        NotificationCenter.default.post(
            name: .readerTextSelection,
            object: nil,
            userInfo: info
        )
    }
}
