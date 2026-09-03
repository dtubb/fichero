@testable import Fichero
import Foundation
import Testing

/// Landing the reader ON the matched passage, and keeping it on the item the
/// user actually picked (Daniel, live 2026-09-03).
///
/// Two defects, one selection flow:
///
///   1. "The reader does not land on the matched passage and does not show
///      what matched." The anchor was posted on `.readerTextSelection` and
///      the reader never subscribed — `updateSourceHighlight(_:)` had no
///      callers at all. Even subscribed, the post arrives BEFORE the pane has
///      the document's text, so a match-or-drop handler drops every one.
///
///   2. "The reader shows the first page of the item's original folder, not
///      the selected result." A reader page signal rewrote `browserSelection`
///      to the matched page's PARENT whenever the parent was a result row;
///      that promotes the container to `detailDocument` and re-roots the
///      reader onto the folder.
@MainActor
struct ReaderSearchPassageLandingTests {

    // MARK: - The anchor is a value, and it survives arriving early

    @Test("the anchor reads the documentId, text and offsets off the seam")
    func anchorParsesTheNotificationPayload() {
        let anchor = ReaderPassageAnchor(userInfo: [
            "documentId": "page-7",
            "text": "the road to Bagadó",
            "charStart": 120,
            "charEnd": 138
        ])
        #expect(anchor?.documentId == "page-7")
        #expect(anchor?.text == "the road to Bagadó")
        #expect(anchor?.charStart == 120)
        #expect(anchor?.charEnd == 138)
    }

    /// Offsets mean nothing without the document they index into. An anchor
    /// that cannot name one must not be applied to whatever is on screen —
    /// that is how the reader highlights the wrong page.
    @Test("an anchor naming no document is not an anchor")
    func anchorRejectsAPayloadWithNoDocument() {
        #expect(ReaderPassageAnchor(userInfo: ["text": "orphan"]) == nil)
        #expect(ReaderPassageAnchor(userInfo: ["documentId": ""]) == nil)
        #expect(ReaderPassageAnchor(userInfo: nil) == nil)
    }

    /// `NSNumber`-shaped offsets arrive whenever the payload has crossed an
    /// `Any` boundary; they are the same numbers.
    @Test("offsets arriving as NSNumber read as the same integers")
    func anchorReadsNSNumberOffsets() {
        let anchor = ReaderPassageAnchor(userInfo: [
            "documentId": "page-7",
            "text": "x",
            "charStart": NSNumber(value: 4),
            "charEnd": NSNumber(value: 9)
        ])
        #expect(anchor?.charStart == 4)
        #expect(anchor?.charEnd == 9)
    }

    /// The anchor hands the SHARED matcher its dictionary, so a search
    /// passage and a claim source can never disagree about where a span is.
    @Test("the anchor's highlight info drives the shared span matcher")
    func anchorHighlightInfoMatchesTheSpan() {
        let content = "Before. the road to Bagadó. After."
        let start = content.range(of: "the road to Bagadó")!
        let anchor = ReaderPassageAnchor(
            documentId: "page-7",
            text: "the road to Bagadó",
            charStart: start.lowerBound.utf16Offset(in: content),
            charEnd: start.upperBound.utf16Offset(in: content)
        )
        let highlight = PageContentClaimSourceHighlight.match(
            content: content, documentId: "page-7", info: anchor.highlightInfo
        )
        #expect(highlight?.highlighted == "the road to Bagadó")
    }

    /// The offsets belong to a version of the text that has since changed
    /// (a re-transcription, an entry rendered from a different source). The
    /// excerpt itself is the fallback, so the passage still lights.
    @Test("stale offsets fall back to finding the excerpt text")
    func anchorFallsBackToTheExcerptWhenOffsetsAreStale() {
        let anchor = ReaderPassageAnchor(
            documentId: "page-7",
            text: "the road to Bagadó",
            charStart: 9_000,
            charEnd: 9_100
        )
        let highlight = PageContentClaimSourceHighlight.match(
            content: "Before. the road to Bagadó. After.",
            documentId: "page-7",
            info: anchor.highlightInfo
        )
        #expect(highlight?.highlighted == "the road to Bagadó")
    }

    /// An anchor is never applied to a document it does not name.
    @Test("an anchor never lights a passage in a different document")
    func anchorDoesNotMatchAnotherDocument() {
        let anchor = ReaderPassageAnchor(
            documentId: "page-7", text: "Bagadó", charStart: nil, charEnd: nil
        )
        let highlight = PageContentClaimSourceHighlight.match(
            content: "a page mentioning Bagadó",
            documentId: "page-99",
            info: anchor.highlightInfo
        )
        #expect(highlight == nil)
    }

    // MARK: - The reader must not answer its own post

    /// `.readerTextSelection` is a shared seam and the reader PUBLISHES on it
    /// (`postReaderSelection`, so the preview can light the matching word
    /// boxes). Only a post that asks the reader to LAND is a landing —
    /// otherwise every cursor drag would swap the selectable text view for
    /// the static highlighted rendering and destroy the selection that
    /// caused it.
    @Test("a plain selection report is not a landing request")
    func aSelectionReportIsNotALanding() {
        let selectionReport: [AnyHashable: Any] = [
            "documentId": "page-7", "text": "dragged", "charStart": 0, "charEnd": 7
        ]
        #expect(!ReaderPassageAnchor.isPassageLanding(selectionReport))

        var landing = selectionReport
        landing[ReaderPassageAnchor.kindKey] = ReaderPassageAnchor.searchPassageKind
        #expect(ReaderPassageAnchor.isPassageLanding(landing))
    }

    /// The shell's search anchor carries the marker, so the wiring is real
    /// rather than a type that merely could be marked.
    @Test("the shell marks its search passage anchor as a landing request")
    func theShellMarksItsSearchAnchor() throws {
        let source = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent("Views/Shell/ContentView/ContentView+StateEvents.swift"),
            encoding: .utf8
        )
        let post = try #require(
            source.components(separatedBy: "func postSearchPassageAnchor(for doc: Document?) {")
                .dropFirst().first
        )
        let body = String(post.prefix(1600))
        #expect(body.contains("ReaderPassageFocus.record(anchor)"))
        #expect(body.contains("ReaderPassageAnchor.kindKey"))
    }

    /// The reader is on the other end of the seam at last — the subscription
    /// whose absence was the whole defect.
    @Test("the reader subscribes to the passage seam")
    func theReaderSubscribesToThePassageSeam() throws {
        let source = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent("Views/Reader/Page/PageContentPane.swift"),
            encoding: .utf8
        )
        #expect(source.contains("publisher(for: .readerTextSelection)"))
        #expect(source.contains("updateSourceHighlight(note)"))
        // The re-application points: the text arriving, and the document
        // changing. Without them an anchor that arrives early is still lost.
        #expect(source.contains("applyPendingPassageAnchor()"))
        #expect(source.contains("adoptLatestPassageAnchor()"))
    }

    // MARK: - The latch: an anchor posted before the reader exists

    /// Selecting a search result builds the reader and posts the anchor in
    /// the same turn, so a pane that only subscribed missed the very post it
    /// subscribed for. The latch is what it reads on appear.
    @Test("the latch holds the last anchor for a reader that mounts later")
    func latchHoldsTheAnchorForALateMount() {
        ReaderPassageFocus.reset()
        #expect(ReaderPassageFocus.latest == nil)
        let anchor = ReaderPassageAnchor(
            documentId: "page-7", text: "Bagadó", charStart: 1, charEnd: 7
        )
        ReaderPassageFocus.record(anchor)
        #expect(ReaderPassageFocus.latest == anchor)
        ReaderPassageFocus.reset()
    }

    /// Once the passage has been shown the anchor is spent — a later,
    /// unrelated mount must not re-land on a search the user has left.
    @Test("consuming the latch clears only the document that used it")
    func latchIsConsumedByTheDocumentThatUsedIt() {
        ReaderPassageFocus.reset()
        ReaderPassageFocus.record(
            ReaderPassageAnchor(
                documentId: "page-7", text: "Bagadó", charStart: 1, charEnd: 7
            )
        )
        ReaderPassageFocus.consume(documentId: "page-99")
        #expect(ReaderPassageFocus.latest != nil)
        ReaderPassageFocus.consume(documentId: "page-7")
        #expect(ReaderPassageFocus.latest == nil)
    }

    // MARK: - The reader stays on the item the user picked

    /// The defect, stated as a test. The page the reader scrolled to is NOT
    /// itself a result; its parent folder IS. The old rule selected the
    /// parent, which promoted the folder to `detailDocument` and re-rooted
    /// the reader onto it — Daniel's "shows the first page of the item's
    /// original folder".
    @Test("a reader page signal never selects the containing folder mid-search")
    func readerPageSignalNeverSelectsTheParentDuringSearch() {
        let selection = ContentView.readerPageSelectionId(
            pageId: "page-7",
            isSearching: true,
            searchResultIds: ["folder-1", "doc-2"]
        )
        #expect(selection == nil)
    }

    /// When the page IS a result row, selecting it is right: the row is
    /// visible and the reader is already showing it.
    @Test("a page that is itself a result row is selected")
    func readerPageSignalSelectsAPageThatIsAResult() {
        let selection = ContentView.readerPageSelectionId(
            pageId: "page-7",
            isSearching: true,
            searchResultIds: ["page-7", "doc-2"]
        )
        #expect(selection == "page-7")
    }

    /// Outside a search the visible rows are the folder's children, so the
    /// page itself is the row to highlight — unchanged behaviour (#1463).
    @Test("outside a search the page itself is the row to select")
    func readerPageSignalSelectsThePageWhenNotSearching() {
        let selection = ContentView.readerPageSelectionId(
            pageId: "page-7", isSearching: false, searchResultIds: []
        )
        #expect(selection == "page-7")
    }
}
