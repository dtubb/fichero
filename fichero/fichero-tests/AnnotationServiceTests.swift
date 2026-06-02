@testable import Fichero
import XCTest

@MainActor
final class AnnotationServiceTests: XCTestCase {

    func testMatchesSearchByText() {
        let annotation = DocumentAnnotation(
            id: "a1",
            documentId: "d1",
            text: "River crossing at Quibdó",
            tags: ["fieldwork"]
        )
        XCTAssertTrue(AnnotationService.matchesSearch(annotation, query: "quibd"))
    }

    func testMatchesSearchByTag() {
        let annotation = DocumentAnnotation(
            id: "a1",
            documentId: "d1",
            text: "note",
            tags: ["speaker-compare"]
        )
        XCTAssertTrue(AnnotationService.matchesSearch(annotation, query: "speaker"))
    }

    func testMatchesSearchByLinkedClaimId() {
        let annotation = DocumentAnnotation(
            id: "a1",
            documentId: "d1",
            text: "note",
            linkedClaimIds: ["claim-abc-123"]
        )
        XCTAssertTrue(AnnotationService.matchesSearch(annotation, query: "abc-123"))
    }

    func testMatchesSearchReturnsFalseWhenNoFieldMatches() {
        let annotation = DocumentAnnotation(
            id: "a1",
            documentId: "d1",
            text: "Local tax records",
            tags: ["archive"]
        )
        XCTAssertFalse(AnnotationService.matchesSearch(annotation, query: "mining"))
    }
}
