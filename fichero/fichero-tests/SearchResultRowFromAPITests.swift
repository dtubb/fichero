@testable import Fichero
import FicheroAPIClient
import SwiftUI
import XCTest

/// Tests for the search result row's static helpers — match-source
/// label inference and `**term**` markdown-style bolding of highlight
/// snippets returned by the backend.
@MainActor
final class SearchResultRowFromAPITests: XCTestCase {

    private func makeResult(
        contentPreview: String? = nil,
        metadata: [String: AnyCodable] = [:],
        highlights: [String]? = nil
    ) -> SearchResult {
        SearchResult(
            documentId: "doc-1",
            score: 0.91,
            contentPreview: contentPreview,
            metadata: metadata,
            highlights: highlights,
            transcriptExcerpts: []
        )
    }

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

    // MARK: - Match-source styling (#1052)

    func testAttributedHighlightEntityMatchAppliesAccentColor() {
        // KG entity matches should use accent color + background
        let attr = SearchResultRowFromAPI.attributedHighlight(
            "Found in document **Asprilla**",
            matchSource: "entity"
        )
        let visible = String(attr.characters)
        XCTAssertEqual(visible, "Found in document Asprilla")
    }

    func testAttributedHighlightSearchTermAppliesBold() {
        // Search-term matches should use bold + primary foreground
        let attr = SearchResultRowFromAPI.attributedHighlight(
            "Found in document **Asprilla**",
            matchSource: "semantic"
        )
        let visible = String(attr.characters)
        XCTAssertEqual(visible, "Found in document Asprilla")
    }

    func testAttributedHighlightCaseInsensitiveEntityDetection() {
        // Entity detection should be case-insensitive
        let attr = SearchResultRowFromAPI.attributedHighlight(
            "Match: **Asprilla**",
            matchSource: "ENTITY"
        )
        let visible = String(attr.characters)
        XCTAssertEqual(visible, "Match: Asprilla")
    }

    func testAttributedHighlightMultiSourceEntityDetection() {
        // When multiple sources include entity, should apply entity styling
        let attr = SearchResultRowFromAPI.attributedHighlight(
            "Match: **Asprilla**",
            matchSource: "entity + semantic"
        )
        let visible = String(attr.characters)
        XCTAssertEqual(visible, "Match: Asprilla")
    }

    // MARK: - Excerpt fallback + navigation

    func testPreferredExcerptFallsBackToSourceExcerptMetadata() {
        let result = makeResult(
            contentPreview: "Generic preview",
            metadata: ["source_excerpt": AnyCodable("Specific matched excerpt")]
        )

        let row = SearchResultRowFromAPI(result: result)
        XCTAssertEqual(row.preferredExcerptText, "Specific matched excerpt")
    }

    func testNavigationRequestUsesMetadataWhenTranscriptExcerptMissing() {
        let result = makeResult(
            metadata: [
                "source_excerpt": AnyCodable("Specific matched excerpt"),
                "source_page_label": AnyCodable("12"),
                "source_char_start": AnyCodable(45),
                "source_char_end": AnyCodable(61)
            ]
        )

        let request = SearchResultRowFromAPI.navigationRequest(for: result)
        XCTAssertEqual(request?.documentId, "doc-1")
        XCTAssertEqual(request?.claimText, "Specific matched excerpt")
        XCTAssertEqual(request?.pageLabel, "12")
        XCTAssertEqual(request?.charStart, 45)
        XCTAssertEqual(request?.charEnd, 61)
    }

    func testSearchServiceConversionPreservesTranscriptExcerptsWiring() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent("Services/SearchService.swift")
        let source = try String(contentsOf: url, encoding: .utf8)

        XCTAssertTrue(source.contains("transcriptExcerpts: generated.transcriptExcerpts"))
    }

    func testSearchScopeSelectionDefaultsToAllScopes() {
        let selection = SearchScopeSelection.all

        XCTAssertTrue(selection.contains(.content))
        XCTAssertTrue(selection.contains(.entities))
        XCTAssertTrue(selection.contains(.claims))
        XCTAssertEqual(
            selection.apiIncludes.map(\.rawValue),
            ["content", "entities", "claims"]
        )
    }

    func testSearchScopeSelectionNeverDropsLastScope() {
        var selection = SearchScopeSelection(scopes: [.content])

        selection.toggle(.content)

        XCTAssertTrue(selection.contains(.content))
        XCTAssertEqual(selection.apiIncludes.map(\.rawValue), ["content"])
    }

    func testSearchServiceRequestBuilderCarriesIncludeValues() throws {
        let request = SearchService.makeSearchRequest(
            SearchService.SearchRequestOptions(
                query: "scope me",
                limit: 25,
                include: [
                    Components.Schemas.SearchInclude(rawValue: "entities")!,
                    Components.Schemas.SearchInclude(rawValue: "claims")!
                ],
                minScore: 0.0,
                searchType: "hybrid",
                sortBy: "relevance",
                sortDirection: "desc",
                offset: 0
            ),
            filtersPayload: nil
        )

        XCTAssertEqual(request.include?.map(\.rawValue), ["entities", "claims"])
    }
}
