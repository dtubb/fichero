@testable import Fichero
import XCTest

/// #4338 — in-reader find: the pure navigation state and the injected
/// find scripts.
@MainActor
final class ReaderFindInPageTests: XCTestCase {

    // MARK: - Wrap-around navigation

    func testWrappedNavigation() {
        XCTAssertEqual(ReaderSearchState.wrapped(2, count: 5), 2)
        XCTAssertEqual(ReaderSearchState.wrapped(6, count: 5), 1, "past the end wraps to the first match")
        XCTAssertEqual(ReaderSearchState.wrapped(0, count: 5), 5, "before the start wraps to the last match")
        XCTAssertEqual(ReaderSearchState.wrapped(1, count: 0), 0, "no matches -> no selection")
    }

    func testRecordMatchesSelectsFirstMatch() {
        let state = ReaderSearchState()
        state.query = "letter"
        state.recordMatches(14)
        XCTAssertEqual(state.matchCount, 14)
        XCTAssertEqual(state.currentIndex, 1)
        XCTAssertEqual(state.statusText, "1 of 14")

        state.next()
        XCTAssertEqual(state.currentIndex, 2)
        state.previous()
        state.previous()
        XCTAssertEqual(state.currentIndex, 14, "previous from the first match wraps to the last")
    }

    func testNoMatchesStatusAndNegativeCountClamped() {
        let state = ReaderSearchState()
        state.query = "zzz"
        state.recordMatches(0)
        XCTAssertEqual(state.statusText, "No matches")
        state.recordMatches(-3)
        XCTAssertEqual(state.matchCount, 0)
        state.next()
        XCTAssertEqual(state.currentIndex, 0, "navigation is inert with no matches")
    }

    func testDismissClearsEverything() {
        let state = ReaderSearchState()
        state.isActive = true
        state.query = "abc"
        state.recordMatches(3)
        state.dismiss()
        XCTAssertEqual(state.query, "")
        XCTAssertEqual(state.matchCount, 0)
        XCTAssertEqual(state.currentIndex, 0)
        XCTAssertFalse(state.isActive)
        XCTAssertEqual(state.statusText, "", "inactive find shows no status")
    }

    // MARK: - Script builders

    func testFindScriptEscapesTheQuery() {
        let script = DocumentKGPaneRoute.findScript(query: "o'brien \\ test")
        XCTAssertTrue(script.contains("__ficheroFind('o\\'brien \\\\ test')"), "quotes and backslashes must be escaped")
        XCTAssertTrue(script.contains("CSS.highlights"), "highlighting uses the CSS Custom Highlight API — no DOM mutation")
    }

    func testFindSelectScriptClampsNegativeIndex() {
        XCTAssertTrue(DocumentKGPaneRoute.findSelectScript(index: -4).contains("__ficheroFindSelect(0)"))
        XCTAssertTrue(DocumentKGPaneRoute.findSelectScript(index: 3).contains("__ficheroFindSelect(3)"))
    }

    func testFindScriptDefinesFinderIdempotently() {
        let script = DocumentKGPaneRoute.findScript(query: "x")
        XCTAssertTrue(script.contains("if (!window.__ficheroFind)"), "the finder installs once per page")
        XCTAssertTrue(script.contains("return window.__ficheroFind("), "the script returns the match count")
    }
}
