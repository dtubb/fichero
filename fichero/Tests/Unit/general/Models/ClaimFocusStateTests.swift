@testable import Fichero
import Foundation
import XCTest

/// ClaimFocusState — cross-pane claim highlighting. Since #3034 the inspector
/// calls `selectClaim` directly (no NotificationCenter bus), so these lock the
/// field-setting contract: a full select sets every field, a partial select
/// clears the unset ones, reselecting the same claim is stable, and
/// clearSelection resets everything. Fresh instances keep cases isolated.
@MainActor
final class ClaimFocusStateTests: XCTestCase {
    func testSelectClaimSetsEveryField() {
        let state = ClaimFocusState()
        state.selectClaim(
            claimId: "c1",
            claimText: "the claim",
            sourceDocumentId: "d1",
            pageLabel: "p3",
            charStart: 10,
            charEnd: 42
        )
        XCTAssertEqual(state.selectedClaimId, "c1")
        XCTAssertEqual(state.selectedClaimText, "the claim")
        XCTAssertEqual(state.selectedClaimSourceDocumentId, "d1")
        XCTAssertEqual(state.selectedClaimPageLabel, "p3")
        XCTAssertEqual(state.selectedClaimCharStart, 10)
        XCTAssertEqual(state.selectedClaimCharEnd, 42)
        XCTAssertTrue(state.isClaimSelected("c1"))
        XCTAssertFalse(state.isClaimSelected("other"))
    }

    /// A later select with only a claimId must not leave the previous select's
    /// text/source/range attached (the defaults are nil).
    func testSelectClaimWithDefaultsClearsStaleFields() {
        let state = ClaimFocusState()
        state.selectClaim(claimId: "c1", claimText: "t", sourceDocumentId: "d", pageLabel: "p")
        state.selectClaim(claimId: "c2")
        XCTAssertEqual(state.selectedClaimId, "c2")
        XCTAssertNil(state.selectedClaimText)
        XCTAssertNil(state.selectedClaimSourceDocumentId)
        XCTAssertNil(state.selectedClaimPageLabel)
        XCTAssertNil(state.selectedClaimCharStart)
        XCTAssertNil(state.selectedClaimCharEnd)
    }

    func testReselectSameClaimIsStable() {
        let state = ClaimFocusState()
        state.selectClaim(claimId: "c1", claimText: "t")
        state.selectClaim(claimId: "c1", claimText: "t")
        XCTAssertEqual(state.selectedClaimId, "c1")
        XCTAssertTrue(state.isClaimSelected("c1"))
    }

    func testClearSelectionResetsEveryField() {
        let state = ClaimFocusState()
        state.selectClaim(claimId: "c1", claimText: "t", sourceDocumentId: "d", pageLabel: "p", charStart: 1, charEnd: 2)
        state.clearSelection()
        XCTAssertNil(state.selectedClaimId)
        XCTAssertNil(state.selectedClaimText)
        XCTAssertNil(state.selectedClaimSourceDocumentId)
        XCTAssertNil(state.selectedClaimPageLabel)
        XCTAssertNil(state.selectedClaimCharStart)
        XCTAssertNil(state.selectedClaimCharEnd)
        XCTAssertFalse(state.isClaimSelected("c1"))
    }
}
