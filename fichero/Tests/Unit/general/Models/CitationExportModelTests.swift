@testable import Fichero
import XCTest

/// CitationExportModel — loads BibTeX for the citation-export affordance
/// (#3451). Locks the phase machine: a non-empty payload is ready to share,
/// blank is empty, a throw is a failure, and a cancellation never overwrites a
/// newer load with an error.
@MainActor
final class CitationExportModelTests: XCTestCase {

    func testCitationDropAssociatesOnlyNewPersistedCitations() {
        let ids = CitationStore.associationIDs(
            from: [
                .init(id: "citation-1", sourceDocumentId: "source", targetDocumentId: nil, text: "Ada, 1843"),
                .init(id: "citation-1", sourceDocumentId: "source", targetDocumentId: nil, text: "duplicate"),
                .init(id: "", sourceDocumentId: "source", targetDocumentId: nil, text: "unsaved"),
                .init(id: "citation-2", sourceDocumentId: "target", targetDocumentId: nil, text: "self"),
                .init(id: "citation-3", sourceDocumentId: "source", targetDocumentId: "target", text: "already associated")
            ],
            targetDocumentId: "target"
        )

        XCTAssertEqual(ids, ["citation-1"])
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
