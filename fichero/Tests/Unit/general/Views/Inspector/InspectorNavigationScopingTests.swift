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

    // MARK: - Active-surface pin ⇄ active reconciliation (#3580, §2.3)

    func testSoleUnpinnedPaneAutoActivates() {
        // No dead state: one unpinned Preview/Reader pane ⇒ it is active without
        // any direct click (§2.3).
        let state = ActiveSurfaceState()
        let a = SurfaceID()
        state.registerUnpinned(a)
        XCTAssertEqual(state.activeSurfaceId, a)
    }

    func testTwoPanesLeaveActiveToTheDirectClick() {
        // With more than one unpinned pane there is no sole winner — active is
        // only set by an explicit click, not by mounting.
        let state = ActiveSurfaceState()
        let a = SurfaceID(), b = SurfaceID()
        state.registerUnpinned(a)   // a auto-active (sole so far)
        state.registerUnpinned(b)   // now two — active stays on a
        XCTAssertEqual(state.activeSurfaceId, a)
        state.activate(b)
        XCTAssertEqual(state.activeSurfaceId, b)
    }

    func testPinningActiveClearsItThenHandsSurvivorTheSlot() {
        // Pin the active pane: it stops following selection (active clears), and
        // the lone remaining unpinned pane silently becomes active (§2.3 reqs 1+2).
        let state = ActiveSurfaceState()
        let a = SurfaceID(), b = SurfaceID()
        state.registerUnpinned(a)
        state.registerUnpinned(b)
        state.activate(b)
        XCTAssertEqual(state.activeSurfaceId, b)

        state.unregister(b)  // b pins → leaves the pool
        XCTAssertEqual(state.activeSurfaceId, a, "sole survivor auto-activates")
    }

    func testClickOnPinnedPaneIsSkipped() {
        // A pinned pane (never registered / already unregistered) is never picked
        // as a new active target (§2.1).
        let state = ActiveSurfaceState()
        let a = SurfaceID(), pinned = SurfaceID()
        state.registerUnpinned(a)
        state.activate(pinned)  // pinned isn't in the pool
        XCTAssertEqual(state.activeSurfaceId, a, "click on a pinned pane must not steal active")
    }

    func testAllPanesPinnedLeavesNoActive() {
        // Every pane pinned ⇒ nothing follows selection ⇒ no active indicator.
        let state = ActiveSurfaceState()
        let a = SurfaceID()
        state.registerUnpinned(a)
        state.unregister(a)
        XCTAssertNil(state.activeSurfaceId)
    }

    func testTwoActiveSurfaceStatesAreIndependent() {
        // Per-window scoping (#3437): activating a pane in window A must not
        // touch window B.
        let windowA = ActiveSurfaceState()
        let windowB = ActiveSurfaceState()
        let a = SurfaceID()
        windowA.registerUnpinned(a)
        XCTAssertEqual(windowA.activeSurfaceId, a)
        XCTAssertNil(windowB.activeSurfaceId, "an active pane in window A must not light up window B")
    }
}
