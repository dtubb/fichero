@testable import Fichero
import FicheroAPIClient
import XCTest

/// PredictionDisplay — flattening a PyKEEN stored prediction for the review row
/// (#3447). Locks the top-candidate selection (best rank wins), the confidence
/// formatting, and the verified state so predicted rows read correctly and
/// distinctly from asserted claims.
final class PredictionDisplayTests: XCTestCase {

    private func result(rank: Int, name: String, confidence: Double) -> Components.Schemas.PredictionResult {
        Components.Schemas.PredictionResult(
            rank: rank,
            score: confidence,
            entityId: "ent-\(name)",
            entityName: name,
            confidence: confidence
        )
    }

    private func prediction(
        results: [Components.Schemas.PredictionResult],
        verified: Bool? = nil
    ) -> Components.Schemas.StoredPrediction {
        Components.Schemas.StoredPrediction(
            predictionId: "pred-1",
            modelId: "model-1",
            createdAt: "2026-07-11T00:00:00Z",
            sourceEntityId: "Ada Lovelace",
            targetEntityId: nil,
            relation: "collaborated with",
            predictionType: .tailPrediction,
            predictions: results,
            verified: verified,
            notes: nil
        )
    }

    func testPicksBestRankedCandidate() {
        let display = PredictionDisplay(prediction(results: [
            result(rank: 3, name: "Babbage", confidence: 0.4),
            result(rank: 1, name: "Somerville", confidence: 0.82),
            result(rank: 2, name: "De Morgan", confidence: 0.6)
        ]))
        XCTAssertEqual(display?.predictedEntityName, "Somerville")
        XCTAssertEqual(display?.confidencePercent, "82%")
    }

    func testNoCandidatesReturnsNil() {
        XCTAssertNil(PredictionDisplay(prediction(results: [])))
    }

    func testVerifiedState() {
        let accepted = PredictionDisplay(prediction(results: [result(rank: 1, name: "X", confidence: 0.5)], verified: true))
        XCTAssertEqual(accepted?.isVerified, true)
        let unreviewed = PredictionDisplay(prediction(results: [result(rank: 1, name: "X", confidence: 0.5)]))
        XCTAssertEqual(unreviewed?.isVerified, false, "nil verified reads as not-yet-reviewed")
    }

    func testConfidenceClamped() {
        let over = PredictionDisplay(prediction(results: [result(rank: 1, name: "X", confidence: 1.4)]))
        XCTAssertEqual(over?.confidencePercent, "100%")
    }
}
