@testable import Fichero
import Foundation
import XCTest

/// Daniel, 2026-09-02: "the user must SEE what ran and why a result matched."
///
/// The engine now says when it found nothing that literally matched and is
/// showing the nearest pages instead (`weak_semantic_only`). A header reading
/// "45 results" over that state claims 45 matches the search never made —
/// the exact confidence lie the honesty surface exists to end. The wording IS
/// the ruling, so the wording is what is pinned.
final class SearchHonestySummaryTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private static let barSource = "Views/Shell/ContentView/ContentView+SearchResultsBar.swift"

    // MARK: - The ordinary headline is unchanged

    func testAnOrdinaryHeadlineStillCountsAndNamesTheScope() {
        XCTAssertEqual(
            SearchHonestySummary.countHeadline(total: 12, query: "Bagadó", scopeName: "Marshall Diaries"),
            "12 results for “Bagadó” in Marshall Diaries"
        )
    }

    func testASingleResultIsNotPluralised() {
        XCTAssertEqual(
            SearchHonestySummary.countHeadline(total: 1, query: "Bagadó", scopeName: "Marshall Diaries"),
            "1 result for “Bagadó” in Marshall Diaries"
        )
    }

    // MARK: - The weak headline claims nothing

    func testAWeakResultSetIsNotCalledResults() {
        let headline = SearchHonestySummary.weakHeadline(total: 45, bestSimilarity: 0.73)

        XCTAssertEqual(headline, "No exact matches — showing the 45 closest pages (closest 73%)")
        // The word that would be the lie.
        XCTAssertFalse(headline.contains("45 results"))
    }

    func testTheWeakHeadlineNamesTheBestSimilarityItActuallyAchieved() {
        XCTAssertTrue(
            SearchHonestySummary.weakHeadline(total: 8, bestSimilarity: 0.6149).contains("closest 61%")
        )
        // Rounded, not truncated — 0.735 is 74%, not 73%.
        XCTAssertTrue(
            SearchHonestySummary.weakHeadline(total: 8, bestSimilarity: 0.735).contains("closest 74%")
        )
    }

    /// An engine that reports the flag but no similarity still gets the
    /// honest sentence — minus a number it did not give.
    func testTheWeakHeadlineSurvivesAMissingSimilarity() {
        XCTAssertEqual(
            SearchHonestySummary.weakHeadline(total: 3, bestSimilarity: nil),
            "No exact matches — showing the 3 closest pages"
        )
    }

    func testASingleClosestPageIsNotPluralised() {
        XCTAssertEqual(
            SearchHonestySummary.weakHeadline(total: 1, bestSimilarity: nil),
            "No exact matches — showing the closest page"
        )
    }

    // MARK: - The legs line

    func testTheLegsLineNamesEveryLegIncludingTheZeroes() {
        XCTAssertEqual(
            SearchHonestySummary.legsLine(
                legs: ["semantic": 45, "fulltext": 0, "kg": 0], graphLegEnabled: false
            ),
            "45 semantic · 0 keyword · graph off"
        )
    }

    /// A zero keyword leg is the whole point: it is what explains why the
    /// results look nothing like the words you typed.
    func testAZeroKeywordLegIsStatedNotOmitted() {
        XCTAssertEqual(
            SearchHonestySummary.legsLine(legs: ["semantic": 45], graphLegEnabled: false),
            "45 semantic · 0 keyword · graph off"
        )
    }

    func testTheGraphLegCountsOnlyWhenItActuallyRan() {
        XCTAssertEqual(
            SearchHonestySummary.legsLine(
                legs: ["semantic": 10, "fulltext": 4, "kg": 3], graphLegEnabled: true
            ),
            "10 semantic · 4 keyword · 3 graph"
        )
        // Same counts, leg not enabled: the number is not shown as if it ran.
        XCTAssertEqual(
            SearchHonestySummary.legsLine(
                legs: ["semantic": 10, "fulltext": 4, "kg": 3], graphLegEnabled: false
            ),
            "10 semantic · 4 keyword · graph off"
        )
    }

    /// An older engine reports no legs. Saying nothing beats inventing
    /// "0 semantic · 0 keyword" it never measured.
    func testAnEngineThatReportsNoLegsSaysNothing() {
        XCTAssertNil(SearchHonestySummary.legsLine(legs: nil, graphLegEnabled: false))
        XCTAssertNil(SearchHonestySummary.legsLine(legs: [:], graphLegEnabled: true))
    }

    func testPercentLabelIsWholeNumbersOnly() {
        XCTAssertEqual(SearchHonestySummary.percentLabel(0.7312), "73%")
        XCTAssertEqual(SearchHonestySummary.percentLabel(1.0), "100%")
        XCTAssertNil(SearchHonestySummary.percentLabel(nil))
    }

    // MARK: - The bar actually uses them

    func testTheHeaderSwitchesToTheWeakWordingOnTheEnginesFlag() throws {
        let source = try Self.appSource(Self.barSource)

        XCTAssertTrue(source.contains("stats.weakSemanticOnly"))
        XCTAssertTrue(source.contains("SearchHonestySummary.weakHeadline("))
        XCTAssertTrue(source.contains("bestSimilarity: stats.bestSemanticSimilarity"))
        // The count sentence is no longer hand-built in the view — one
        // spelling, in one place, for both headlines.
        XCTAssertTrue(source.contains("SearchHonestySummary.countHeadline("))
    }

    func testTheLegsLineIsMountedUnderTheHeader() throws {
        let source = try Self.appSource(Self.barSource)

        XCTAssertTrue(source.contains("retrievalLegsRow(store: store)"))
        XCTAssertTrue(source.contains("SearchHonestySummary.legsLine("))
        XCTAssertTrue(source.contains("library.search.legs"))
    }

    /// The line describes a COMPLETED retrieval or it says nothing — never a
    /// leg count over a failure or an in-flight query.
    func testTheLegsLineIsAbsentOverAFailureOrAnInFlightQuery() throws {
        let source = try Self.appSource(Self.barSource)

        let row = try XCTUnwrap(
            source.components(separatedBy: "private func retrievalLegsRow").dropFirst().first
        )
        let body = String(row.prefix(500))
        XCTAssertTrue(body.contains("store.searchFailure == nil"))
        XCTAssertTrue(body.contains("!store.isSearching"))
    }
}
