@testable import Fichero
import XCTest

/// CitationExportModel — loads BibTeX for the citation-export affordance
/// (#3451). Locks the phase machine: a non-empty payload is ready to share,
/// blank is empty, a throw is a failure, and a cancellation never overwrites a
/// newer load with an error.
@MainActor
final class CitationExportModelTests: XCTestCase {

    func testCitationDragPayloadRoundTripsAcrossTargets() throws {
        let payload = CitationDragID(id: "citation-1", text: "Ada, 1843")
        let decoded = try JSONDecoder().decode(CitationDragID.self, from: JSONEncoder().encode(payload))

        XCTAssertEqual(decoded.id, "citation-1")
        XCTAssertEqual(decoded.text, "Ada, 1843")
    }

    func testReadyWithBibTeX() async {
        let model = CitationExportModel()
        await model.load { "@article{key, title={T}}" }
        XCTAssertEqual(model.phase, .ready("@article{key, title={T}}"))
    }

    func testBlankIsEmpty() async {
        let model = CitationExportModel()
        await model.load { "   \n" }
        XCTAssertEqual(model.phase, .empty)
    }

    func testThrowIsFailed() async {
        struct Boom: Error {}
        let model = CitationExportModel()
        await model.load { throw Boom() }
        XCTAssertEqual(model.phase, .failed)
    }

    func testCancellationDoesNotFail() async {
        let model = CitationExportModel()
        await model.load { throw CancellationError() }
        XCTAssertNotEqual(model.phase, .failed)
    }
}
