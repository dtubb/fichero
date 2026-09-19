@testable import Fichero
import Foundation
import XCTest

/// Tests for KGFocusState — cross-view knowledge-graph focus (entity/claim +
/// source document/page). Locks the focus transitions: focusing an entity
/// clears any focused claim, focusing a claim can co-set its entity, and clear
/// resets every field. Uses fresh instances (not the `shared` singleton) so the
/// cases stay isolated.
@MainActor
final class KGFocusStateTests: XCTestCase {

    func testFocusEntitySetsFieldsAndClearsClaim() {
        let state = KGFocusState()
        // #4834: entityId has no default any more — explicit nil, matching
        // this fresh state's already-nil entity (no behavior change here).
        state.focusClaim(claimId: "cl-1", entityId: nil)
        XCTAssertEqual(state.focusedClaimId, "cl-1")

        state.focusEntity(entityId: "e-1", sourceDocumentId: "d-1", sourcePageLabel: "p1")
        XCTAssertEqual(state.focusedEntityId, "e-1")
        XCTAssertNil(state.focusedClaimId, "focusing an entity must clear the claim")
        XCTAssertEqual(state.sourceDocumentId, "d-1")
        XCTAssertEqual(state.sourcePageLabel, "p1")
    }

    func testFocusClaimCanCoSetEntity() {
        let state = KGFocusState()
        state.focusClaim(claimId: "cl-2", entityId: "e-2")
        XCTAssertEqual(state.focusedClaimId, "cl-2")
        XCTAssertEqual(state.focusedEntityId, "e-2")
    }

    func testFocusEntityWithoutSourceResetsSourceFields() {
        let state = KGFocusState()
        state.focusEntity(entityId: "e", sourceDocumentId: "d", sourcePageLabel: "p")
        XCTAssertEqual(state.sourceDocumentId, "d")

        // A later focus with no source must not leave the stale source attached.
        state.focusEntity(entityId: "e2")
        XCTAssertEqual(state.focusedEntityId, "e2")
        XCTAssertNil(state.sourceDocumentId)
        XCTAssertNil(state.sourcePageLabel)
    }

    func testClearResetsEveryField() {
        let state = KGFocusState()
        state.focusEntity(entityId: "e", sourceDocumentId: "d", sourcePageLabel: "p")
        state.clear()
        XCTAssertNil(state.focusedEntityId)
        XCTAssertNil(state.focusedClaimId)
        XCTAssertNil(state.sourceDocumentId)
        XCTAssertNil(state.sourcePageLabel)
    }

    // MARK: - Compact push bridge (#3011)

    /// Pushing an entity leaf focuses it (leaf resolution).
    func testSyncPushedEntityFocusesTheLeaf() {
        let state = KGFocusState()
        state.syncPushedEntity("e-42")
        XCTAssertEqual(state.focusedEntityId, "e-42")
    }

    /// Popping the entity detail (a `nil` leaf) clears KG focus so the list
    /// returns unfocused — the core #3011 pop-clears-focus guarantee.
    func testSyncPushedEntityNilClearsFocus() {
        let state = KGFocusState()
        state.focusEntity(entityId: "e-1", sourceDocumentId: "d-1", sourcePageLabel: "p1")

        state.syncPushedEntity(nil)
        XCTAssertNil(state.focusedEntityId)
        XCTAssertNil(state.focusedClaimId)
        XCTAssertNil(state.sourceDocumentId)
        XCTAssertNil(state.sourcePageLabel)
    }

    /// Pushing a different entity retargets focus (list → detail → back → detail).
    func testSyncPushedEntityRetargetsToNewLeaf() {
        let state = KGFocusState()
        state.syncPushedEntity("e-1")
        state.syncPushedEntity("e-2")
        XCTAssertEqual(state.focusedEntityId, "e-2")
    }

    // MARK: - Graph reveal request (#3452)

    /// "Show in Graph" focuses the entity and bumps the reveal token so
    /// ContentView switches into the force graph.
    func testRequestGraphRevealFocusesEntityAndBumpsToken() {
        let state = KGFocusState()
        let before = state.graphRevealRequestToken

        state.requestGraphReveal(entityId: "e-9")

        XCTAssertEqual(state.focusedEntityId, "e-9")
        XCTAssertEqual(state.graphRevealRequestToken, before + 1)
    }

    /// Revealing the SAME entity twice still bumps the token, so a repeat
    /// "Show in Graph" re-triggers the mode switch.
    func testRepeatGraphRevealStillBumpsToken() {
        let state = KGFocusState()
        state.requestGraphReveal(entityId: "e-1")
        let afterFirst = state.graphRevealRequestToken

        state.requestGraphReveal(entityId: "e-1")
        XCTAssertEqual(state.graphRevealRequestToken, afterFirst + 1)
    }

    // MARK: - Cross-window handoff (#4850)

    override func tearDown() {
        // `.shared` is a real, process-wide singleton — clear it so one
        // test's handoff can never leak into the next.
        KGFocusState.shared.clear()
        super.tearDown()
    }

    /// The core #4850 fix, pinned structurally: the entity inspector's
    /// library-resolving `entityService` and the entities table's own must
    /// come from the SAME per-window source — `ContentView` owns its
    /// `kgFocusState` (`@State`), it does not read the app-wide `.shared`
    /// singleton (`@Environment`). Source-scan because the actual defect was
    /// architectural (which object a whole window's subtree inherits), not a
    /// single computable value a fresh `KGFocusState()` could pin on its own.
    func testContentViewOwnsItsOwnPerWindowKGFocusState() throws {
        let source = try AppSource.code("Views/Shell/ContentView/ContentView.swift")
        XCTAssertTrue(
            source.contains("@State var kgFocusState = KGFocusState()"),
            "ContentView must OWN a fresh per-window KGFocusState, matching entitySearchState/claimSourceNavigationState — not read the app-wide .shared singleton via @Environment"
        )
        XCTAssertFalse(
            source.contains("@Environment(KGFocusState.self) var kgFocusState"),
            "a click in one window's Entities table must never drive a different window's Inspector again"
        )
    }

    /// A window opened via "Open in New Window/Tab" (#1685) must still
    /// auto-focus the claim/entity that opened it — the ONE case the shared
    /// singleton is deliberately still used for, now as an explicit one-shot
    /// mailbox rather than an ambiently-read value.
    func testHandOffToNewWindowIsConsumedByTheReceivingWindowOnly() {
        let opener = KGFocusState()
        opener.focusClaim(claimId: "cl-1", entityId: "e-1")

        KGFocusState.handOffToNewWindow(
            entityId: "e-1", claimId: "cl-1", sourceDocumentId: "d-1", sourcePageLabel: "12r"
        )

        let newWindow = KGFocusState()
        newWindow.consumePendingHandoff()
        XCTAssertEqual(newWindow.focusedEntityId, "e-1")
        XCTAssertEqual(newWindow.focusedClaimId, "cl-1")
        XCTAssertEqual(newWindow.sourceDocumentId, "d-1")
        XCTAssertEqual(newWindow.sourcePageLabel, "12r")
    }

    /// A pending hand-off is consumed exactly ONCE — a THIRD window (or the
    /// same window re-appearing) must never inherit a stale value.
    func testHandOffIsClearedAfterConsumingSoAThirdWindowGetsNothing() {
        KGFocusState.handOffToNewWindow(
            entityId: "e-1", claimId: nil, sourceDocumentId: nil, sourcePageLabel: nil
        )

        let secondWindow = KGFocusState()
        secondWindow.consumePendingHandoff()
        XCTAssertEqual(secondWindow.focusedEntityId, "e-1")

        let thirdWindow = KGFocusState()
        thirdWindow.consumePendingHandoff()
        XCTAssertNil(thirdWindow.focusedEntityId, "the hand-off must be consumed once, not re-readable")
    }

    /// No pending hand-off — a window opened normally (not via Open in New
    /// Window) must not pick up stale focus from an unrelated prior hand-off.
    func testConsumePendingHandoffIsANoOpWhenNothingIsPending() {
        let window = KGFocusState()
        window.consumePendingHandoff()
        XCTAssertNil(window.focusedEntityId)
        XCTAssertNil(window.focusedClaimId)
    }
}
