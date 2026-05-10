@testable import Fichero
import SwiftUI
import XCTest

/// Tests for the search result row's static helpers — match-source
/// label inference and `**term**` markdown-style bolding of highlight
/// snippets returned by the backend.
final class SearchResultRowFromAPITests: XCTestCase {

    // MARK: - attributedHighlight

    func testAttributedHighlightPreservesPlainText() {
        let attr = SearchResultRowFromAPI.attributedHighlight(
            "plain text with no markers"
        )
        XCTAssertEqual(String(attr.characters), "plain text with no markers")
    }

    func testAttributedHighlightStripsAsterisks() {
        // The backend writes `**term**` markers around the matched span.
        // We render that as bold but the asterisks themselves must NOT
        // appear in the visible string — that's the regression Daniel
        // would catch if we ever fell back to plain text rendering.
        let attr = SearchResultRowFromAPI.attributedHighlight(
            "es, the response of **Colombia**n governments has be"
        )
        let visible = String(attr.characters)
        XCTAssertFalse(visible.contains("**"))
        XCTAssertEqual(
            visible,
            "es, the response of Colombian governments has be"
        )
    }

    func testAttributedHighlightHandlesMultipleSpans() {
        let attr = SearchResultRowFromAPI.attributedHighlight(
            "**Asprilla** lives in **Quibdó**"
        )
        let visible = String(attr.characters)
        XCTAssertEqual(visible, "Asprilla lives in Quibdó")
    }

    func testAttributedHighlightHandlesUnclosedMarker() {
        // Defensive: if the backend emits an unbalanced `**`, we should
        // render what's there without crashing.
        let attr = SearchResultRowFromAPI.attributedHighlight(
            "**Asprilla without closing"
        )
        let visible = String(attr.characters)
        // The opening asterisks are stripped + everything after is bold
        // (or just rendered) — but no crash.
        XCTAssertFalse(visible.contains("**"))
    }

    func testAttributedHighlightEmptyInput() {
        let attr = SearchResultRowFromAPI.attributedHighlight("")
        XCTAssertEqual(String(attr.characters), "")
    }

    func testAttributedHighlightLeadingAndTrailingMarkers() {
        let attr = SearchResultRowFromAPI.attributedHighlight(
            "**Asprilla** and others **lived here**"
        )
        let visible = String(attr.characters)
        XCTAssertEqual(visible, "Asprilla and others lived here")
    }
}
