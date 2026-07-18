@testable import Fichero
import FicheroAPIClient
import XCTest

@MainActor
final class ImageEditOperationDisplayTests: XCTestCase {
    /// #3028: the migration routes chain ops through the generated client, which
    /// models operations as free-form `OpenAPIObjectContainer`. The bridge must
    /// round-trip the app's `AnyCodable` ops losslessly — including unknown keys
    /// (e.g. `derived_path`) and value types (Int stays Int) — so the UI and the
    /// PUT-back-to-`/edits` remove flow keep working.
    func testChainBridgeRoundTripsFreeFormOperationLosslessly() throws {
        let op = AnyCodable([
            "op": "crop",
            "page": 2,
            "derived_path": "/derived/x.png",  // unknown key must survive the round-trip
            "params": [
                "left": 1, "top": 2, "width": 300, "height": 400
            ] as [String: Any]
        ] as [String: Any])

        // AnyCodable -> generated upsert payloads (the PUT body direction).
        let upsertOps = try ImageEditingServiceGenerated.generatedOps([op])
        XCTAssertEqual(upsertOps.count, 1)

        // Generated response -> AnyCodable (the GET/response decode direction).
        let response = Components.Schemas.ImageEditChainResponse(
            documentId: "doc-1",
            operations: upsertOps.map { .init(additionalProperties: $0.additionalProperties) },
            updatedAt: Date(timeIntervalSince1970: 0)
        )
        let chain = try ImageEditingServiceGenerated.chain(from: response)

        XCTAssertEqual(chain.documentId, "doc-1")
        XCTAssertEqual(chain.operations.count, 1)
        let round = chain.operations[0]
        XCTAssertEqual(round.opKind, "crop")
        XCTAssertEqual(round.page, 2)
        XCTAssertEqual(round.params["width"] as? Int, 300)
        let dict = round.raw.value as? [String: Any]
        XCTAssertEqual(dict?["derived_path"] as? String, "/derived/x.png")
    }

    func testFuzzyCleanDisplaysReadableTitleIconAndSummary() {
        let operation = ImageEditOperation(raw: AnyCodable([
            "op": "fuzzy_clean",
            "page": 1,
            "params": [
                "despeckle_radius": 3,
                "background_clean": true
            ] as [String: Any]
        ] as [String: Any]))

        XCTAssertEqual(operation.title, "Despeckle")
        XCTAssertEqual(operation.icon, "sparkles")
        XCTAssertEqual(operation.summary, "despeckle 3, background clean")
    }

    func testEnhanceSummaryIncludesWorkflowDenoiseParameter() {
        let operation = ImageEditOperation(raw: AnyCodable([
            "op": "enhance",
            "page": 1,
            "params": [
                "brightness": 1.0,
                "contrast": 1.5,
                "sharpen": 1.25,
                "auto_levels": false,
                "denoise": true
            ] as [String: Any]
        ] as [String: Any]))

        XCTAssertEqual(operation.summary, "contrast 1.5, sharpen 1.2, denoise")
    }
}
