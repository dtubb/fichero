@testable import Fichero
import Foundation
import XCTest

/// The cross-cutting source-navigation contract (#2105/#3437). A request now
/// carries the source region (`bbox`), the resolved `pageIndex`, and a
/// `destination` intent (preview / reader / both) alongside the pre-existing
/// char-range fields. These lock the additive shape so the provenance popover
/// (#3449) and reveal-in-preview can rely on it, and confirm the request state
/// still rejects empty document ids and bumps its id on every accepted request.
@MainActor
final class SourceNavigationContractTests: XCTestCase {

    func testRequestCarriesBboxPageAndIntent() {
        let request = ClaimSourceNavigationRequest(
            documentId: "doc-1",
            claimId: "claim-9",
            claimText: "Person P says XYZ",
            pageLabel: "12",
            pageIndex: 11,
            charStart: 3,
            charEnd: 40,
            bbox: [0.1, 0.2, 0.5, 0.35],
            destination: .preview
        )
        XCTAssertEqual(request.bbox, [0.1, 0.2, 0.5, 0.35])
        XCTAssertEqual(request.pageIndex, 11)
        XCTAssertEqual(request.destination, .preview)
    }

    func testDestinationDefaultsToReader() {
        // Additive default preserves the legacy jump-to-page behaviour: callers
        // that don't opt into preview still drive the reader.
        let request = ClaimSourceNavigationRequest(documentId: "doc-1")
        XCTAssertEqual(request.destination, .reader)
        XCTAssertNil(request.bbox)
        XCTAssertNil(request.pageIndex)
    }

    func testEquatableDistinguishesBbox() {
        let base = ClaimSourceNavigationRequest(documentId: "doc-1", bbox: [0, 0, 1, 1])
        var other = base
        other.bbox = [0, 0, 1, 0.5]
        XCTAssertNotEqual(base, other)
    }

    func testStateStoresRequestAndBumpsID() {
        let state = ClaimSourceNavigationState()
        XCTAssertEqual(state.requestID, 0)
        XCTAssertNil(state.currentRequest)

        let request = ClaimSourceNavigationRequest(
            documentId: "doc-1", bbox: [0, 0, 1, 1], destination: .both
        )
        state.request(request)
        XCTAssertEqual(state.requestID, 1)
        XCTAssertEqual(state.currentRequest, request)

        state.request(request)
        XCTAssertEqual(state.requestID, 2, "each accepted request bumps the id even if identical")
    }

    func testStateRejectsBlankDocumentId() {
        let state = ClaimSourceNavigationState()
        state.request(ClaimSourceNavigationRequest(documentId: "   "))
        XCTAssertEqual(state.requestID, 0)
        XCTAssertNil(state.currentRequest)
    }
}
