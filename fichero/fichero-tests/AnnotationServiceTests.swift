@testable import Fichero
import XCTest

@MainActor
final class AnnotationServiceTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testAnnotationServiceWiresDetailCropAndPromoteEndpoints() throws {
        let source = try Self.appSource("Services/AnnotationService.swift")

        XCTAssertTrue(source.contains("/api/annotations/\\(id)"))
        XCTAssertTrue(source.contains("/api/annotations/\\(id)/crop"))
        XCTAssertTrue(source.contains("/api/annotations/\\(id)/promote-to-claim"))
        XCTAssertTrue(source.contains("method: \"PATCH\""))
        XCTAssertTrue(source.contains("method: \"DELETE\""))
        XCTAssertTrue(source.contains("method: \"POST\""))
    }

    func testDocumentInspectorAnnotationsTabWiresRowActions() throws {
        let source = try Self.appSource("Views/Library/DocumentInspector/DocumentInspectorAnnotationsTab.swift")

        XCTAssertTrue(source.contains("service.getAnnotation(id: annotation.id)"))
        XCTAssertTrue(source.contains("service.updateText(id: annotation.id, text: editText)"))
        XCTAssertTrue(source.contains("service.cropAnnotation(id: annotation.id)"))
        XCTAssertTrue(source.contains("service.promoteToClaim(id: annotation.id)"))
        XCTAssertTrue(source.contains("service.delete(id: annotation.id)"))
    }

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
