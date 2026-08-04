@testable import Fichero
import Foundation
import XCTest

/// #4357 — per-document work shown in place: the run's pages (and only those)
/// carry progress, and the reader is updated by patching changed pages, never
/// by reloading the WebKit view.
@MainActor
final class ReaderPageProgressTests: XCTestCase {

    private func page(
        _ id: String,
        sequence: Int?,
        content: String? = nil,
        docType: DocType = .page
    ) -> Document {
        Document(
            id: id,
            parentId: "pdf-1",
            docType: docType,
            name: id,
            sequence: sequence,
            pageContent: content
        )
    }

    // MARK: - Only the run's pages show progress

    func testBusyPagesAreOnlyTheRunTargets() {
        let children = [
            page("p1", sequence: 1),
            page("p2", sequence: 2),
            page("p3", sequence: 3)
        ]
        let busy = ReaderPageProgress.busyPageNumbers(children: children) { id in
            id == "p2"
        }
        XCTAssertEqual(busy, [2], "only the page the run targets is working")
    }

    func testPageWithoutSequenceIsNeverMarkedBusy() {
        // No position means no page to highlight — a spinner on the wrong page
        // is worse than no spinner.
        let children = [page("p-unknown", sequence: nil)]
        let busy = ReaderPageProgress.busyPageNumbers(children: children) { _ in true }
        XCTAssertTrue(busy.isEmpty)
    }

    func testNonPageChildrenAreIgnored() {
        let children = [
            page("child-artifact", sequence: 1, docType: .file),
            page("p2", sequence: 2)
        ]
        let busy = ReaderPageProgress.busyPageNumbers(children: children) { _ in true }
        XCTAssertEqual(busy, [2])
    }

    // MARK: - Live content is scoped and diffed

    func testLivePageContentCoversOnlyTrackedPages() {
        let children = [
            page("p1", sequence: 1, content: "first"),
            page("p2", sequence: 2, content: "second"),
            page("p3", sequence: 3)
        ]
        let content = ReaderPageProgress.livePageContent(children: children, pages: [2, 3])
        XCTAssertEqual(content, [2: "second", 3: ""], "an untranscribed tracked page is empty, not missing")
    }

    func testOnlyChangedPagesArePatched() {
        let latest = [1: "same", 2: "new text"]
        let lastSent = [1: "same", 2: "old text"]
        XCTAssertEqual(
            ReaderPageProgress.changedPatches(latest: latest, lastSent: lastSent),
            [2: "new text"],
            "an unchanged page produces no JS call at all"
        )
        XCTAssertTrue(
            ReaderPageProgress.changedPatches(latest: latest, lastSent: latest).isEmpty
        )
    }

    func testFirstPatchOfAPageIsSentEvenWhenEmpty() {
        XCTAssertEqual(
            ReaderPageProgress.changedPatches(latest: [4: ""], lastSent: [:]),
            [4: ""],
            "a page cleared by a re-run must reach the reader too"
        )
    }

    // MARK: - Tracking survives the run ending

    func testTrackedPagesKeepPagesAfterTheRunFinishes() {
        var tracked = ReaderPageProgress.trackedPages(alreadyTracked: [], busy: [2])
        XCTAssertEqual(tracked, [2])
        // The run reaches a terminal state: the busy set empties, but page 2
        // must keep receiving its final write.
        tracked = ReaderPageProgress.trackedPages(alreadyTracked: tracked, busy: [])
        XCTAssertEqual(tracked, [2])
        tracked = ReaderPageProgress.trackedPages(alreadyTracked: tracked, busy: [5])
        XCTAssertEqual(tracked, [2, 5])
    }

    // MARK: - Injected scripts

    func testBusyPagesScriptSendsASortedList() {
        XCTAssertEqual(
            DocumentKGPaneRoute.busyPagesScript([3, 1]),
            "window.fichero?.setBusyPages([1,3]);"
        )
        XCTAssertEqual(
            DocumentKGPaneRoute.busyPagesScript([]),
            "window.fichero?.setBusyPages([]);",
            "an empty set clears every spinner — a spinner that cannot stop is worse than none"
        )
    }

    func testPageContentScriptEscapesTheText() {
        let script = DocumentKGPaneRoute.pageContentScript(page: 2, content: "it's\nhere")
        XCTAssertEqual(script, "window.fichero?.setPageContent(2, 'it\\'s\\nhere');")
    }
}
