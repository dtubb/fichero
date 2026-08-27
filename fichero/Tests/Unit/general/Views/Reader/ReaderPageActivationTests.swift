@testable import Fichero
import Foundation
import Testing

/// #4373: clicking a page in the reader must select that page in the library
/// AND move the preview — one click, every surface follows.
///
/// Daniel's acceptance is a correctness test for the *seam*, not a feature
/// list: if the click routes through the single shared selection path, the
/// sidebar highlight, the preview and the inspector all update as observers
/// with no extra wiring. Anything that lags means a parallel navigation was
/// introduced instead.
@MainActor
struct ReaderPageActivationTests {

    // MARK: - What each signal may move (#4373 over #1463)

    /// Superseded ruling, updated 2026-08-09: Daniel, twice — "if you change
    /// page in the preview it should change selection in the library". BOTH
    /// signals move the browser selection now; what protects a user-built
    /// multi-selection is applyReaderPageSignal's own guard (only a click may
    /// replace a selection larger than one), not this policy bit.
    @Test("both signals move the library selection (2026-08-09 ruling)")
    func bothSignalsMoveTheBrowserSelection() {
        #expect(ReaderPageSignal.clicked.movesBrowserSelection)
        #expect(ReaderPageSignal.scrolledPast.movesBrowserSelection)
    }

    @Test("both signals move the page-focus cursor that drives preview and inspector")
    func bothSignalsMovePageFocus() {
        #expect(ReaderPageSignal.clicked.movesPageFocus)
        #expect(ReaderPageSignal.scrolledPast.movesPageFocus)
    }

    /// The invariant that must never regress: re-rooting the previewed document
    /// reloads the WebKit transcript underneath the click that was meant to
    /// move within it (#1463).
    @Test("neither signal ever re-roots the previewed document")
    func neitherSignalRerootsThePreviewedDocument() {
        for signal in [ReaderPageSignal.clicked, .scrolledPast] {
            #expect(!signal.rerootsPreviewedDocument, "\(signal)")
        }
    }

    // MARK: - The activation bus

    @Test("an activation records the page and advances the request id")
    func activationRecordsThePage() {
        let state = ReaderPageActivationState()
        #expect(state.currentRequest == nil)
        #expect(state.requestID == 0)

        #expect(state.activate(pageNumber: 3))
        #expect(state.currentRequest == ReaderPageActivation(pageNumber: 3))
        #expect(state.requestID == 1)
    }

    /// Clicking the page you are already on is still a request to select it —
    /// the observer watches `requestID`, so the second click must not be
    /// swallowed as "no change".
    @Test("clicking the same page twice fires twice")
    func repeatedActivationOfTheSamePageFiresAgain() {
        let state = ReaderPageActivationState()
        #expect(state.activate(pageNumber: 3))
        let first = state.requestID
        #expect(state.activate(pageNumber: 3))
        #expect(state.requestID == first + 1)
        #expect(state.currentRequest == ReaderPageActivation(pageNumber: 3))
    }

    /// Rule zero: a malformed payload is REJECTED and reported, never clamped
    /// to page 1. Quietly selecting a different page than the one clicked is
    /// exactly the sort of wrong answer that makes a navigation bug unfindable.
    @Test("a non-positive page number is rejected, never clamped to page 1")
    func malformedPageNumbersAreRejected() {
        let state = ReaderPageActivationState()
        for bad in [0, -1, -99] {
            #expect(!state.activate(pageNumber: bad), "page \(bad) must be rejected")
        }
        #expect(state.currentRequest == nil)
        #expect(state.requestID == 0)
    }

    @Test("page numbers are 1-based and the index is 0-based")
    func pageNumberToIndex() {
        #expect(ReaderPageActivation(pageNumber: 1).pageIndex == 0)
        #expect(ReaderPageActivation(pageNumber: 3).pageIndex == 2)
    }

    /// The round trip the click actually performs: a 1-based transcript page
    /// resolves to the page child whose `sequence` matches it, through the SAME
    /// resolver the scroll path uses.
    ///
    /// #4532 — the "fails at runtime while statically correct" mystery was the
    /// FIXTURE, found by compiling the pieces standalone: with the closure
    /// parameter unannotated, Swift's contravariant closure inference typed it
    /// `Int?` (because `Document.sequence` is `Int?`, and `(Int?) -> Document`
    /// satisfies `map`'s `(Int) -> Document`), so every interpolated id became
    /// "page-Optional(1)" while `sequence` still stored 1. The resolver then
    /// returned the RIGHT document with a poisoned id, and
    /// `resolved?.id == "page-1"` failed on every row. The explicit
    /// `(sequence: Int)` annotation forbids that inference; the id pin below
    /// names the failure if it ever comes back.
    @Test("an activation resolves to the page child the scroll path would find")
    func activationResolvesThroughTheSharedResolver() {
        let pages = (1...4).map { (sequence: Int) in
            Document(
                id: "page-\(sequence)",
                docType: .page,
                name: "Page \(sequence)",
                sequence: sequence
            )
        }
        #expect(
            pages.map(\.id) == ["page-1", "page-2", "page-3", "page-4"],
            "fixture ids are \(pages.map(\.id)) — closure-parameter inference regressed to Int?"
        )

        for pageNumber in 1...4 {
            let activation = ReaderPageActivation(pageNumber: pageNumber)
            let resolved = ContentView.pageDocument(atPDFIndex: activation.pageIndex, in: pages)
            #expect(
                resolved?.id == "page-\(pageNumber)",
                "pageNumber \(pageNumber) → index \(activation.pageIndex) resolved \(resolved?.id ?? "nil")"
            )
        }
    }

    /// The reported symptom: page 3 was empty and clicking it did nothing.
    /// An untranscribed page is still a page child with a sequence, so
    /// resolution must not depend on it having any content — the reason to
    /// resolve by structure rather than by text.
    @Test("an empty, untranscribed page resolves exactly like a full one")
    func anEmptyPageResolvesLikeAnyOther() {
        let pages = [
            Document(id: "page-1", docType: .page, name: "Page 1", sequence: 1),
            Document(id: "page-2", docType: .page, name: "Page 2", sequence: 2),
            // No content of any kind — the #4373 repro.
            Document(id: "page-3", docType: .page, name: "Page 3", sequence: 3),
        ]
        let resolved = ContentView.pageDocument(
            atPDFIndex: ReaderPageActivation(pageNumber: 3).pageIndex,
            in: pages
        )
        #expect(resolved?.id == "page-3")
    }

    // MARK: - The selected-page border cannot go stale (#4373)

    /// The failure that matters: if the cursor moves and the border does not,
    /// the reader is lying about which page is selected. The highlight is
    /// therefore sent under EVERY suppression condition — suppression exists
    /// for the scroll, never for the border.
    @Test("a moved cursor always moves the border, whatever is suppressed")
    func aMovedCursorAlwaysMovesTheBorder() {
        for suppressed in [true, false] {
            for webDriving in [true, false] {
                let decision = ReaderActivePageSync.decide(
                    lastSent: 2,
                    desired: 5,
                    isScrollSuppressed: suppressed,
                    isWebDriving: webDriving
                )
                #expect(
                    decision.sendsHighlight,
                    "suppressed: \(suppressed), webDriving: \(webDriving)")
            }
        }
    }

    /// The precise old bug: the value was recorded as delivered before two
    /// early returns, so a suppressed tick marked the border sent and left it
    /// on the wrong page forever. Recording and sending are now the same
    /// condition.
    @Test("nothing is ever recorded as sent unless it was sent")
    func neverRecordsWhatItDidNotSend() {
        let lastValues: [Int?] = [nil, 1, 2, 7]
        let desiredValues: [Int?] = [nil, 1, 2, 7]
        for lastSent in lastValues {
            for desired in desiredValues {
                for suppressed in [true, false] {
                    for webDriving in [true, false] {
                        let decision = ReaderActivePageSync.decide(
                            lastSent: lastSent,
                            desired: desired,
                            isScrollSuppressed: suppressed,
                            isWebDriving: webDriving
                        )
                        #expect(decision.recordsAsSent == decision.sendsHighlight)
                        // And a scroll is never sent without the highlight that
                        // justifies it.
                        if decision.sendsScroll {
                            #expect(decision.sendsHighlight)
                        }
                    }
                }
            }
        }
    }

    /// Clicking the page you are already reading: the cursor does not move, so
    /// nothing is redrawn — and nothing needs to be, because the border is
    /// already on that page. The confirmation the user sees is that it stays.
    @Test("a repeated click on the already-selected page redraws nothing")
    func repeatedClickOnTheCurrentPageIsANoOp() {
        let decision = ReaderActivePageSync.decide(
            lastSent: 3,
            desired: 3,
            isScrollSuppressed: true,
            isWebDriving: false
        )
        #expect(!decision.sendsHighlight)
        #expect(!decision.sendsScroll)
    }

    /// Scrolling after a click must move the border with the scroll — the two
    /// intents share the page-focus cursor, so the border follows both.
    @Test("scrolling after a click moves the border to the scrolled-to page")
    func scrollingAfterAClickMovesTheBorder() {
        let decision = ReaderActivePageSync.decide(
            lastSent: 3,
            desired: 4,
            isScrollSuppressed: false,
            isWebDriving: true
        )
        #expect(decision.sendsHighlight)
        // …but the web view is already at that page, so it is not re-scrolled.
        #expect(!decision.sendsScroll)
    }

    /// A click comes from inside the transcript, so the page is already on
    /// screen: border yes, scroll no. Without this the click yanks the page to
    /// the top of the viewport and moves the text out from under the pointer.
    @Test("a click moves the border without re-scrolling the transcript")
    func clickMovesTheBorderWithoutScrolling() {
        let decision = ReaderActivePageSync.decide(
            lastSent: 5,
            desired: 2,
            isScrollSuppressed: true,
            isWebDriving: false
        )
        #expect(decision.sendsHighlight)
        #expect(!decision.sendsScroll)
    }

    /// A cursor change driven from OUTSIDE the reader — a sidebar or preview
    /// click — has to bring the page into view, because the user is not
    /// looking at it yet.
    @Test("an externally driven change both borders and scrolls")
    func externallyDrivenChangeScrolls() {
        let decision = ReaderActivePageSync.decide(
            lastSent: 1,
            desired: 9,
            isScrollSuppressed: false,
            isWebDriving: false
        )
        #expect(decision.sendsHighlight)
        #expect(decision.sendsScroll)
    }

    /// After a transcript reload the coordinator clears `lastActivePageNumber`,
    /// so the first sync re-sends and the border is restored at the same page
    /// rather than silently missing.
    @Test("the border is redrawn after a transcript reload")
    func borderSurvivesAReload() {
        let afterReload = ReaderActivePageSync.decide(
            lastSent: nil,
            desired: 4,
            isScrollSuppressed: false,
            isWebDriving: false
        )
        #expect(afterReload.sendsHighlight)
    }

    /// A cursor that becomes nil clears the border instead of stranding it on
    /// a page that is no longer selected.
    @Test("a nil cursor clears the border rather than stranding it")
    func nilCursorClearsTheBorder() {
        let decision = ReaderActivePageSync.decide(
            lastSent: 4,
            desired: nil,
            isScrollSuppressed: false,
            isWebDriving: false
        )
        #expect(decision.sendsHighlight)
        #expect(!decision.sendsScroll, "there is nowhere to scroll to")
        #expect(ReaderActivePageSync.highlightScript(page: nil).contains("null"))
    }

    @Test("the highlight script addresses the page by number, not by a new scheme")
    func highlightScriptUsesTheExistingBridge() {
        let script = ReaderActivePageSync.highlightScript(page: 7)
        #expect(script == "window.fichero?.setActivePage(7);")
        #expect(
            ReaderActivePageSync.scrollScript(page: 7, pageCount: 12)
                == "window.ficheroScrollToPage?.(7, 12);"
        )
    }

    // MARK: - Structural: one seam, not a parallel navigation

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// The border must be driven from the page-focus cursor, not set in the
    /// click handler — a second source of truth for "which page is selected"
    /// is the exact defect #4380 spent three commits removing from the
    /// connection surfaces.
    @Test("the border is driven from the cursor, never from the click handler")
    func borderIsDrivenFromTheCursorNotTheClick() throws {
        for coordinator in [
            "Views/Reader/Knowledge/DocumentKGWebPaneCoordinatorMacOS.swift",
            "Views/Reader/Knowledge/DocumentKGWebPaneCoordinatoriOS.swift",
        ] {
            let source = try Self.appSource(coordinator)
            // The highlight goes out from the cursor sync…
            #expect(source.contains("ReaderActivePageSync.decide("), Comment(rawValue: coordinator))
            #expect(source.contains("ReaderActivePageSync.highlightScript("), Comment(rawValue: coordinator))
            // …and the value is recorded only after the guard, never before it.
            let syncBody = source.components(separatedBy: "func syncActivePage(")[1]
            let guardIndex = syncBody.range(of: "guard decision.sendsHighlight")
            let recordIndex = syncBody.range(of: "lastActivePageNumber = parent.activePageNumber")
            #expect(guardIndex != nil, Comment(rawValue: coordinator))
            #expect(recordIndex != nil, Comment(rawValue: coordinator))
            if let guardIndex, let recordIndex {
                #expect(guardIndex.lowerBound < recordIndex.lowerBound, Comment(rawValue: coordinator))
            }
            // The click handler must NOT set the highlight itself.
            let clickBody = source.components(separatedBy: "func handlePageActivated(")[1]
            #expect(!clickBody.contains("setActivePage"), Comment(rawValue: coordinator))
            #expect(!clickBody.contains("highlightScript"), Comment(rawValue: coordinator))
        }
    }

    /// A click and a scroll must share one application point. Two separate
    /// bodies would drift, which is the whole reason this issue exists.
    @Test("click and scroll are applied by the same function")
    func clickAndScrollShareOneApplicationPoint() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView+ReadingLayout.swift")
        #expect(source.contains("func applyReaderPageSignal("))
        #expect(source.contains("applyReaderPageSignal(.scrolledPast"))
        #expect(source.contains("applyReaderPageSignal(.clicked"))
        // The #1463 invariant, asserted structurally: this function must not
        // assign detailDocument at all.
        #expect(!source.contains("detailDocument = match"))
    }

    /// The bridge must distinguish the two intents. One message kind carrying a
    /// flag would let a scroll re-use the click's privileges by accident.
    @Test("the web bridge posts a distinct kind for a click")
    func theBridgePostsADistinctKindForAClick() throws {
        let scripts = try Self.appSource("Views/Reader/Knowledge/DocumentKGWebPane+Scripts.swift")
        #expect(scripts.contains("kind: 'pageActivated'"))
        #expect(scripts.contains("kind: 'pageSelected'"))
        // Dragging to select text is reading, not navigating.
        #expect(scripts.contains("selection.isCollapsed"))
        // The click listener must survive the single-page early return that
        // scroll sync takes.
        #expect(scripts.contains("installPageClicks()"))

        for coordinator in [
            "Views/Reader/Knowledge/DocumentKGWebPaneCoordinatorMacOS.swift",
            "Views/Reader/Knowledge/DocumentKGWebPaneCoordinatoriOS.swift",
        ] {
            let source = try Self.appSource(coordinator)
            #expect(source.contains("case \"pageActivated\":"), Comment(rawValue: coordinator))
            #expect(source.contains("handlePageActivated(body)"), Comment(rawValue: coordinator))
        }
    }

    /// Per-window, never `.shared` — the #3437 scoping invariant the other two
    /// reader/inspector buses already hold to.
    @Test("the activation bus is per-window, not a process-global singleton")
    func theBusIsPerWindow() throws {
        let source = try Self.appSource("Views/Reader/ReaderPageActivationState.swift")
        #expect(!source.contains("static let shared"))
        let contentView = try Self.appSource("Views/Shell/ContentView/ContentView.swift")
        #expect(contentView.contains("@State var readerPageActivationState = ReaderPageActivationState()"))
        let root = try Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
        #expect(root.contains(".environment(readerPageActivationState)"))
        #expect(root.contains("handleReaderPageActivated()"))
    }
}
