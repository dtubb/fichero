@testable import Fichero
import XCTest

/// Per-window scoping of the inspector request buses (#3437). Each window's
/// ContentView owns its own EntitySearchState / ClaimSourceNavigationState
/// instance (no more process-global `.shared`), so a search or source reveal in
/// one window must never bump the other window's request id. These lock that
/// isolation at the state level, without a full UI test.
@MainActor
final class InspectorNavigationScopingTests: XCTestCase {

    func testTwoSearchStatesAreIndependent() {
        let windowA = EntitySearchState()
        let windowB = EntitySearchState()

        windowA.request(name: "Ada Lovelace", entityType: "people")

        XCTAssertEqual(windowA.requestID, 1)
        XCTAssertEqual(windowA.requestedName, "Ada Lovelace")
        XCTAssertEqual(windowB.requestID, 0, "a search in window A must not touch window B")
        XCTAssertNil(windowB.requestedName)
    }

    func testTwoSourceNavStatesAreIndependent() {
        let windowA = ClaimSourceNavigationState()
        let windowB = ClaimSourceNavigationState()

        windowA.request(ClaimSourceNavigationRequest(documentId: "doc-1", bbox: [0, 0, 1, 1]))

        XCTAssertEqual(windowA.requestID, 1)
        XCTAssertEqual(windowA.currentRequest?.documentId, "doc-1")
        XCTAssertEqual(windowB.requestID, 0, "a reveal in window A must not navigate window B")
        XCTAssertNil(windowB.currentRequest)
    }

    func testSearchStateIsNotAProcessSingleton() {
        // Fresh instances start clean — proving there's no shared global carrying
        // state across windows.
        XCTAssertEqual(EntitySearchState().requestID, 0)
        XCTAssertEqual(ClaimSourceNavigationState().requestID, 0)
    }
}
