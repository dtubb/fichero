@testable import Fichero
import Foundation
import XCTest

/// Daniel, 2026-09-02: "the tiers are a ladder — Full text / Semantic /
/// Semantic+Graph — the user must SEE what ran and why a result matched";
/// "with no graph or garbage entities the graph must be OFF"; "logical
/// defaults (hybrid)".
///
/// The ladder itself is pure and tested directly. Its presentation — three
/// checked rows, the graph rung able to go dead WITH a reason — is pinned by
/// source scan, the way this suite pins every other chrome invariant.
final class SearchRetrievalTierTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private static let menuSource = "Views/Library/Search/SearchFieldOptionsMenu.swift"
    private static let contentViewSource = "Views/Shell/ContentView/ContentView.swift"

    // MARK: - Three rungs, in cost order

    func testTheLadderIsExactlyThreeRungsBottomFirst() {
        XCTAssertEqual(
            SearchRetrievalTier.ladder,
            [.fulltext, .semantic, .semanticGraph]
        )
        XCTAssertEqual(SearchRetrievalTier.ladder.count, SearchRetrievalTier.allCases.count)
    }

    func testEachRungCarriesTheEngineValueItRequests() {
        XCTAssertEqual(SearchRetrievalTier.fulltext.requestValue, "fulltext")
        XCTAssertEqual(SearchRetrievalTier.semantic.requestValue, "hybrid")
        XCTAssertEqual(SearchRetrievalTier.semanticGraph.requestValue, "hybrid_graph")
    }

    func testTheRungsAreNamedAsTheLadderDanielDescribed() {
        XCTAssertEqual(SearchRetrievalTier.fulltext.title, "Full Text")
        XCTAssertEqual(SearchRetrievalTier.semantic.title, "Semantic")
        XCTAssertEqual(SearchRetrievalTier.semanticGraph.title, "Semantic + Graph")
    }

    /// Every rung explains what it runs — three opaque words are not a ladder.
    func testEveryRungExplainsItself() {
        for tier in SearchRetrievalTier.ladder {
            XCTAssertFalse(tier.help.isEmpty, "\(tier) has no explanation")
        }
    }

    // MARK: - The default is the MIDDLE rung

    /// "Logical defaults (hybrid)" — semantic + keyword fused, not the graph.
    func testTheDefaultTierIsFusedSemanticNotGraph() {
        XCTAssertEqual(SearchRetrievalTier.defaultTier, .semantic)
        XCTAssertEqual(SearchRetrievalTier.defaultTier.requestValue, "hybrid")
    }

    /// …and the state the request is actually built from starts there too, so
    /// the menu's checked row and the first search agree.
    func testTheSearchStateStartsOnTheDefaultTier() throws {
        let source = try Self.appSource(Self.contentViewSource)
        XCTAssertTrue(source.contains("transientSearchType = \"hybrid\""))
    }

    // MARK: - Reading a request value back onto a rung

    func testARequestValueRoundTripsToItsRung() {
        for tier in SearchRetrievalTier.ladder {
            XCTAssertEqual(SearchRetrievalTier(requestValue: tier.requestValue), tier)
        }
    }

    /// A saved search from before the ladder can carry the pure-vector
    /// `"semantic"`, which is not a rung. It shows on the Semantic rung
    /// rather than leaving the menu with nothing checked.
    func testTheLegacyPureVectorValueShowsOnTheSemanticRung() {
        XCTAssertEqual(SearchRetrievalTier(requestValue: "semantic"), .semantic)
    }

    func testAnUnknownValueFallsBackToTheDefaultRungRatherThanNothing() {
        XCTAssertEqual(SearchRetrievalTier(requestValue: "sparkles"), .semantic)
        XCTAssertEqual(SearchRetrievalTier(requestValue: ""), .semantic)
    }

    // MARK: - "With no graph the graph must be OFF"

    func testTheGraphRungIsUnavailableWithNoReviewedEntities() {
        XCTAssertFalse(SearchRetrievalTier.graphTierAvailable(reviewedEntities: 0))
    }

    func testTheGraphRungIsAvailableOnceTheGraphHasReviewedEntities() {
        XCTAssertTrue(SearchRetrievalTier.graphTierAvailable(reviewedEntities: 1))
        XCTAssertTrue(SearchRetrievalTier.graphTierAvailable(reviewedEntities: 4_212))
    }

    /// An UNKNOWN count is not zero. Refusing a tier because we never asked
    /// is a dishonesty of its own, so `nil` keeps the rung live.
    func testAnUnknownEntityCountKeepsTheGraphRungEnabled() {
        XCTAssertTrue(SearchRetrievalTier.graphTierAvailable(reviewedEntities: nil))
    }

    func testTheDeadGraphRungCarriesAReason() {
        XCTAssertTrue(SearchRetrievalTier.noGraphHelp.contains("knowledge-graph"))
        XCTAssertFalse(SearchRetrievalTier.noGraphHelp.isEmpty)
    }

    // MARK: - How the menu renders the ladder

    func testTheMenuRendersTheLadderAndNothingElse() throws {
        let source = try Self.appSource(Self.menuSource)

        XCTAssertTrue(source.contains("ForEach(SearchRetrievalTier.ladder)"))
        // The old flat three-way picker is gone — it could not disable a row.
        XCTAssertFalse(source.contains("Picker(\"Search Type\", selection: $searchType)"))
        XCTAssertFalse(source.contains("Text(\"Hybrid\").tag(\"hybrid\")"))
    }

    /// Radio-style: the selected rung draws a checkmark, and the rung is read
    /// through the ladder rather than compared to a raw string.
    func testTheSelectedRungIsChecked() throws {
        let source = try Self.appSource(Self.menuSource)

        XCTAssertTrue(source.contains("SearchRetrievalTier(requestValue: searchType) == tier"))
        XCTAssertTrue(source.contains("Label(tier.title, systemImage: \"checkmark\")"))
    }

    /// Picking a rung writes the value the next request carries — one source
    /// of truth for what ran.
    func testPickingARungWritesTheRequestValue() throws {
        let source = try Self.appSource(Self.menuSource)

        XCTAssertTrue(source.contains("searchType = tier.requestValue"))
    }

    func testTheGraphRungGoesDeadWithItsExplanation() throws {
        let source = try Self.appSource(Self.menuSource)

        XCTAssertTrue(source.contains("SearchRetrievalTier.graphTierAvailable(reviewedEntities: reviewedEntityCount)"))
        XCTAssertTrue(source.contains(".disabled(!isAvailable)"))
        XCTAssertTrue(source.contains("SearchRetrievalTier.noGraphHelp"))
    }

    /// The count the menu gates on is the engine's own — never a client-side
    /// guess about what the graph holds.
    func testTheEntityCountComesFromTheEngineResponse() throws {
        let bar = try Self.appSource("Views/Shell/ContentView/ContentView+SearchResultsBar.swift")

        XCTAssertTrue(bar.contains("reviewedEntityCount: store.searchStats?.reviewedEntityCount"))
    }
}
