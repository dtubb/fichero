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

    /// The whole policy as a table. A scroll and a click resolve to the same
    /// page document and differ ONLY here.
    @Test("a click moves the library selection; a scroll does not")
    func onlyAClickMovesTheBrowserSelection() {
        #expect(ReaderPageSignal.clicked.movesBrowserSelection)
        #expect(!ReaderPageSignal.scrolledPast.movesBrowserSelection)
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
    @Test("an activation resolves to the page child the scroll path would find")
    func activationResolvesThroughTheSharedResolver() {
        let pages = (1...4).map { sequence in
            Document(
                id: "page-\(sequence)",
                docType: .page,
                name: "Page \(sequence)",
                sequence: sequence
            )
        }
        for pageNumber in 1...4 {
            let activation = ReaderPageActivation(pageNumber: pageNumber)
            let resolved = ContentView.pageDocument(atPDFIndex: activation.pageIndex, in: pages)
            #expect(resolved?.id == "page-\(pageNumber)")
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

    // MARK: - Structural: one seam, not a parallel navigation

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
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
            #expect(source.contains("case \"pageActivated\":"), coordinator)
            #expect(source.contains("handlePageActivated(body)"), coordinator)
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
