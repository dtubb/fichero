@testable import Fichero
import Foundation
import XCTest

/// Daniel, 2026-09-02: the percentage said how WELL a row matched and never
/// how — and worse, it said it dishonestly. The fused rank score renormalises
/// the top hit toward 1.0, so a weak 0.73 cosine neighbour arrived at the row
/// dressed as an 87% match. Two rulings land here:
///
///   * a semantic-only row's badge shows the RAW cosine, and
///   * a row says which legs claimed it — "exact" for the literal words,
///     "graph" for a knowledge-graph connection.
final class SearchMatchProvenanceTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private func result(
        score: Double,
        metadata: [String: Any]
    ) -> SearchResult {
        SearchResult(
            documentId: "doc-1",
            score: score,
            contentPreview: "the road to Bagadó",
            metadata: metadata.mapValues { AnyCodable($0) },
            highlights: nil
        )
    }

    // MARK: - The badge shows the honest number

    /// The defect, stated as a test: fused 0.87, raw cosine 0.73, semantic
    /// leg only. The badge must read 73%.
    func testASemanticOnlyRowShowsItsRawCosineNotTheFusedScore() {
        let hit = result(
            score: 0.87,
            metadata: ["semantic_similarity": 0.73, "match_sources": ["semantic"]]
        ).rowHit(query: "Bagadó")

        XCTAssertTrue(hit.isSemanticOnly)
        XCTAssertEqual(hit.semanticSimilarity, 0.73)
        XCTAssertEqual(hit.displayScore, 0.73)
        XCTAssertEqual(hit.score, 0.87, "the fused score is preserved, just not displayed")
    }

    /// A row with literal evidence WAS ranked against the others by the fused
    /// score, so the fused score is the honest number there.
    func testARowWithLiteralEvidenceKeepsTheFusedScore() {
        let hit = result(
            score: 0.91,
            metadata: ["semantic_similarity": 0.62, "match_sources": ["semantic", "fulltext"]]
        ).rowHit(query: "Bagadó")

        XCTAssertFalse(hit.isSemanticOnly)
        XCTAssertEqual(hit.displayScore, 0.91)
    }

    /// An engine that rides no similarity leaves the badge exactly as it was.
    func testAMissingSimilarityFallsBackToTheScoreItAlwaysShowed() {
        let hit = result(score: 0.55, metadata: ["match_sources": ["semantic"]]).rowHit()

        XCTAssertNil(hit.semanticSimilarity)
        XCTAssertEqual(hit.displayScore, 0.55)
    }

    func testAnIntegerShapedSimilarityStillReads() {
        let hit = result(score: 0.4, metadata: ["semantic_similarity": 1, "match_sources": ["semantic"]])
            .rowHit()

        XCTAssertEqual(hit.semanticSimilarity, 1.0)
        XCTAssertEqual(hit.displayScore, 1.0)
    }

    // MARK: - Which legs claimed the row

    func testMatchSourcesAreReadOffTheEnginesMetadata() {
        let hit = result(score: 0.8, metadata: ["match_sources": ["fulltext", "kg"]]).rowHit()

        XCTAssertEqual(Set(hit.matchSources), [.fulltext, .kg])
    }

    func testAnUnknownLegIsDroppedRatherThanChipped() {
        XCTAssertEqual(SearchMatchSource.parse(["semantic", "telepathy"]), [.semantic])
        XCTAssertEqual(SearchMatchSource.parse([]), [])
    }

    func testARowWithNoMatchSourcesClaimsNoLegs() {
        let hit = result(score: 0.8, metadata: [:]).rowHit()

        XCTAssertEqual(hit.matchSources, [])
        // …and therefore is NOT treated as semantic-only, so its badge keeps
        // the score it always showed.
        XCTAssertFalse(hit.isSemanticOnly)
        XCTAssertEqual(hit.displayScore, 0.8)
    }

    // MARK: - The chips

    /// Semantic earns no chip: it is what the % badge already describes, and
    /// a chip on every row is a chip that says nothing.
    func testOnlyLiteralAndGraphLegsEarnAChip() {
        XCTAssertNil(SearchMatchSource.semantic.chipLabel)
        XCTAssertEqual(SearchMatchSource.fulltext.chipLabel, "exact")
        XCTAssertEqual(SearchMatchSource.kg.chipLabel, "graph")
    }

    func testEveryLegExplainsItselfOnHover() {
        for source in SearchMatchSource.allCases {
            XCTAssertFalse(source.chipHelp.isEmpty, "\(source) has no explanation")
        }
    }

    // MARK: - The row mounts both

    func testTheListRowShowsTheChipsAndTheHonestBadge() throws {
        let source = try Self.appSource("Views/Library/LibraryViewComponents.swift")

        XCTAssertTrue(source.contains("SearchMatchSourceChips(sources: hit.matchSources)"))
        XCTAssertTrue(source.contains("SearchRelevanceBadge(score: hit.displayScore)"))
        // The renormalised number must not survive anywhere on the row.
        XCTAssertFalse(source.contains("SearchRelevanceBadge(score: hit.score)"))
    }

    /// One spelling of the number across view modes — the icon grid mounts
    /// the same badge off the same honest score.
    func testTheIconGridShowsTheSameHonestBadge() throws {
        let source = try Self.appSource("Views/Library/ViewModes/Icon/LibraryView+IconMode.swift")

        XCTAssertTrue(source.contains("SearchRelevanceBadge(score: hit.displayScore)"))
        XCTAssertFalse(source.contains("SearchRelevanceBadge(score: hit.score)"))
    }

    /// A document reached ONLY through an entity or claim hit is a graph
    /// match and says so — the difference between "mentions Bagadó" and
    /// "the graph connected this to Bagadó".
    func testEntityAndClaimRowsAreChippedAsGraphMatches() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView+SearchResults.swift")

        let entity = try XCTUnwrap(
            source.components(separatedBy: "excerpt: entity.canonicalName").dropFirst().first
        )
        XCTAssertTrue(String(entity.prefix(200)).contains("matchSources: [.kg]"))

        let claim = try XCTUnwrap(
            source.components(separatedBy: "excerpt: claim.text").dropFirst().first
        )
        XCTAssertTrue(String(claim.prefix(200)).contains("matchSources: [.kg]"))
    }
}
