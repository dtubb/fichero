@testable import Fichero
import XCTest

/// #4834 — spec `kg.read.sentence-opens-source-highlighted`: the pure rule
/// deciding whether a `kgFocusState` entity/claim focus change should clear
/// `sourceRevealDocument`.
///
/// Corrected 2026-09-19 (maintainer test, finding A1): the ORIGINAL
/// assumption — that the reveal's own `focusClaim` call and the handler
/// clearing `sourceRevealDocument` could only race occasionally, since "the
/// id does not change" on an in-place click — was FALSE. SwiftUI's
/// `onChange` fires only on an actual `Equatable` value change, so before
/// #4834's entity-preserving fix, every reveal that focused a claim wrote
/// the entity from X to `nil` (a real change), reliably firing the
/// `focusedEntityId` onChange and clearing the SAME reveal's
/// `sourceRevealDocument` every time — deterministic, not a race. This is
/// the one shared cause behind BOTH halves of finding A1: the Inspector
/// tearing down (entity cleared) and Preview staying on "No selection"
/// (`sourceRevealDocument` cleared right after being set).
///
/// `ContentView.shouldClearSourceReveal` is the one pure decision both the
/// `focusedEntityId` and `focusedClaimId` `onChange` handlers
/// (`ContentView+RootLayout.swift`) now call, tested here through the REAL
/// function with real inputs — not a source scan.
@MainActor
final class ShouldClearSourceRevealTests: XCTestCase {
    /// No reveal in flight, an entity change: clears, exactly as before
    /// `revealingClaimId` existed — a focus change with nothing revealed has
    /// nothing to protect.
    func testNoRevealInFlightEntityChangeClears() {
        XCTAssertTrue(
            ContentView.shouldClearSourceReveal(
                newClaimId: "claim-1", revealingClaimId: nil, entityChanged: true
            )
        )
    }

    /// No reveal in flight, a claim change: clears, same reasoning.
    func testNoRevealInFlightClaimChangeClears() {
        XCTAssertTrue(
            ContentView.shouldClearSourceReveal(
                newClaimId: "claim-1", revealingClaimId: nil, entityChanged: false
            )
        )
    }

    /// A reveal IS in flight and the change is an ENTITY change: this is the
    /// in-flight reveal's OWN `focusClaim` call setting (or preserving) the
    /// entity it is revealing — must NOT clear the reveal it is in the
    /// middle of. This is the exact case that was wrong before the fix.
    func testRevealInFlightEntityChangeDoesNotClear() {
        XCTAssertFalse(
            ContentView.shouldClearSourceReveal(
                newClaimId: "claim-1", revealingClaimId: "claim-1", entityChanged: true
            )
        )
    }

    /// A reveal is in flight and a DIFFERENT claim is focused: a genuinely
    /// new focus supersedes the in-flight reveal, so it still clears.
    func testRevealInFlightDifferentClaimChangeClears() {
        XCTAssertTrue(
            ContentView.shouldClearSourceReveal(
                newClaimId: "claim-2", revealingClaimId: "claim-1", entityChanged: false
            )
        )
    }

    /// A reveal is in flight and the "new" claim IS the one it is revealing
    /// (its own internal `focusClaim` call firing the claim onChange): must
    /// not clear its own result either.
    func testRevealInFlightSameClaimChangeDoesNotClear() {
        XCTAssertFalse(
            ContentView.shouldClearSourceReveal(
                newClaimId: "claim-1", revealingClaimId: "claim-1", entityChanged: false
            )
        )
    }
}
