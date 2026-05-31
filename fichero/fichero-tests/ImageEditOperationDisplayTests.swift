@testable import Fichero
import XCTest

final class ImageEditOperationDisplayTests: XCTestCase {
    func testFuzzyCleanDisplaysReadableTitleIconAndSummary() {
        let operation = ImageEditOperation(raw: AnyCodable([
            "op": "fuzzy_clean",
            "page": 1,
            "params": [
                "despeckle_radius": 3,
                "background_clean": true
            ] as [String: Any]
        ] as [String: Any]))

        XCTAssertEqual(operation.title, "Fuzzy Clean")
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
