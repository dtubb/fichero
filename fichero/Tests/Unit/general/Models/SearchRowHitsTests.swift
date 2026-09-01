@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

/// Every row the grid shows can say how well it ranked.
///
/// Daniel, 2026-09-01: "some rows show no relevance number". `hitDocumentIds`
/// folds entity- and claim-leg hits into the result set as nodes (#4118), but
/// the per-row hit map was built from the DOCUMENT leg alone — so those rows
/// resolved to `nil` and rendered blank where every other row shows a
/// percentage. `ContentView.rowHits` fills them from the legs' own similarity
/// scores; these tests pin that, and pin that the document leg still wins.
@MainActor
final class SearchRowHitsTests: XCTestCase {

    private func result(_ id: String, score: Double, preview: String) -> SearchResult {
        SearchResult(
            documentId: id,
            score: score,
            contentPreview: preview,
            metadata: [:],
            highlights: nil
        )
    }

    private func response(
        results: [SearchResult],
        entityHits: [Components.Schemas.SearchEntityHit] = [],
        claimHits: [Components.Schemas.SearchClaimHit] = []
    ) -> SearchResponse {
        SearchResponse(
            results: results,
            entityHits: entityHits,
            claimHits: claimHits,
            count: results.count,
            totalResults: results.count,
            query: "dam",
            searchType: "hybrid",
            executionTimeMs: 1,
            hasMore: false,
            filtersApplied: nil,
            suggestions: nil
        )
    }

    func testDocumentLegRowsCarryTheirScore() {
        let results = [result("doc-1", score: 0.82, preview: "the dam")]
        let hits = ContentView.rowHits(results: results, stats: response(results: results))
        XCTAssertEqual(hits["doc-1"]?.score, 0.82)
        XCTAssertEqual(hits["doc-1"]?.excerpt, "the dam")
    }

    func testEntityLegRowGetsAScoreInsteadOfNothing() {
        let entity = Components.Schemas.SearchEntityHit(
            canonicalName: "Mactaquac Dam",
            sourceDocumentIds: ["doc-entity"],
            similarityScore: 0.71
        )
        let hits = ContentView.rowHits(
            results: [], stats: response(results: [], entityHits: [entity])
        )
        XCTAssertEqual(hits["doc-entity"]?.score, 0.71)
        XCTAssertEqual(hits["doc-entity"]?.excerpt, "Mactaquac Dam")
    }

    func testClaimLegRowGetsAScoreInsteadOfNothing() {
        let claim = Components.Schemas.SearchClaimHit(
            text: "The dam was completed in 1968.",
            sourceDocumentId: "doc-claim",
            similarityScore: 0.64
        )
        let hits = ContentView.rowHits(
            results: [], stats: response(results: [], claimHits: [claim])
        )
        XCTAssertEqual(hits["doc-claim"]?.score, 0.64)
        XCTAssertEqual(hits["doc-claim"]?.excerpt, "The dam was completed in 1968.")
    }

    func testDocumentLegWinsWhenTheSameDocumentAlsoMatchedAnEntity() {
        // The fused ranking already counted the entity evidence as its own
        // RRF leg (#1833 M1) — showing the raw entity similarity instead
        // would report a number the ordering does not use.
        let results = [result("doc-1", score: 0.90, preview: "text hit")]
        let entity = Components.Schemas.SearchEntityHit(
            canonicalName: "Mactaquac Dam",
            sourceDocumentIds: ["doc-1"],
            similarityScore: 0.20
        )
        let hits = ContentView.rowHits(
            results: results, stats: response(results: results, entityHits: [entity])
        )
        XCTAssertEqual(hits["doc-1"]?.score, 0.90)
        XCTAssertEqual(hits["doc-1"]?.excerpt, "text hit")
    }

    func testEveryFoldedInHitIdHasARowHit() {
        // The invariant behind the defect: whatever `hitDocumentIds` puts in
        // the grid, `rowHits` can score. If these two ever drift apart again,
        // blank relevance columns come back.
        let results = [result("doc-1", score: 0.5, preview: "a")]
        let entity = Components.Schemas.SearchEntityHit(
            canonicalName: "Entity", sourceDocumentIds: ["doc-2"], similarityScore: 0.4
        )
        let claim = Components.Schemas.SearchClaimHit(
            text: "Claim", sourceDocumentId: "doc-3", similarityScore: 0.3
        )
        let stats = response(results: results, entityHits: [entity], claimHits: [claim])
        let ids = ContentView.hitDocumentIds(results: results, stats: stats)
        let hits = ContentView.rowHits(results: results, stats: stats)
        XCTAssertEqual(ids, ["doc-1", "doc-2", "doc-3"])
        for id in ids {
            XCTAssertNotNil(hits[id], "row \(id) rendered with no relevance number")
        }
    }

    func testNoStatsIsJustTheDocumentLeg() {
        let results = [result("doc-1", score: 0.5, preview: "a")]
        let hits = ContentView.rowHits(results: results, stats: nil)
        XCTAssertEqual(hits.count, 1)
        XCTAssertEqual(hits["doc-1"]?.score, 0.5)
    }

    func testMissingSimilarityScoreIsZeroNotAbsent() {
        // An unscored leg hit still renders a number — 0% is information;
        // a blank cell is the defect.
        let entity = Components.Schemas.SearchEntityHit(
            canonicalName: "Entity", sourceDocumentIds: ["doc-x"]
        )
        let hits = ContentView.rowHits(
            results: [], stats: response(results: [], entityHits: [entity])
        )
        XCTAssertEqual(hits["doc-x"]?.score, 0)
    }
}
