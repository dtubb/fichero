@testable import Fichero
import XCTest

/// #4834 — spec `kg.read.sentence-opens-source-highlighted`: a biography
/// sentence's reveal must not tear down the Inspector's entity arm mid-click.
///
/// Root cause (maintainer test, 2026-09-19, finding A1): `KGFocusState
/// .focusClaim(claimId:entityId:sourceDocumentId:sourcePageLabel:)` defaults
/// `entityId` to `nil` and assigns it UNCONDITIONALLY. The reveal's call at
/// `ContentView+StateEvents.swift` (`handleOpenClaimSource`) used to omit
/// `entityId:`, so every claim-source reveal cleared whatever entity was
/// currently focused — and `DocumentInspector.inspectorArm` treats "no
/// document, no focused entity" as `.empty`, tearing the biography down.
///
/// This test goes through the REAL decision functions the source-scan tests
/// that shipped Slice A did not: it builds a real `KGFocusState`, focuses an
/// entity the way viewing its Inspector arm would, performs the SAME
/// `focusClaim` call the reveal now makes (passing the currently-focused
/// entity, not omitting it), and asserts both that the entity survives and
/// that `DocumentInspector.inspectorArm` — the pure function the Inspector's
/// `body` switches on — still resolves to `.entity`, not `.empty`.
@MainActor
final class RevealPreservesEntityFocusTests: XCTestCase {
    func testClaimRevealPreservesFocusedEntityAndInspectorArmStaysOnEntity() {
        let state = KGFocusState()

        // The Inspector is showing an entity's biography (no document open).
        state.focusEntity(entityId: "entity-antonio", sourceDocumentId: nil, sourcePageLabel: nil)
        XCTAssertEqual(
            DocumentInspector.inspectorArm(hasDocument: false, focusedEntityId: state.focusedEntityId),
            .entity,
            "precondition: the Inspector must start on the entity arm"
        )

        // The exact call `handleOpenClaimSource` now makes when a biography
        // sentence's source is opened: `entityId:` is the CURRENTLY focused
        // entity, not omitted.
        state.focusClaim(
            claimId: "claim-1",
            entityId: state.focusedEntityId,
            sourceDocumentId: "doc-source-1",
            sourcePageLabel: "12r"
        )

        XCTAssertEqual(
            state.focusedEntityId, "entity-antonio",
            "a claim-source reveal must not clear the entity that was already focused"
        )
        XCTAssertEqual(
            DocumentInspector.inspectorArm(hasDocument: false, focusedEntityId: state.focusedEntityId),
            .entity,
            "the Inspector must stay on the entity arm through the reveal, not tear down to .empty"
        )
    }

    /// The trap this regression came from, pinned directly: omitting
    /// `entityId:` (its default) on an ALREADY-focused entity clears it. This
    /// is the exact call shape Slice A shipped; it must keep failing this way
    /// until the API itself changes, so a future caller cannot reintroduce it
    /// unknowingly.
    func testOmittingEntityIdOnAnAlreadyFocusedEntityClearsIt() {
        let state = KGFocusState()
        state.focusEntity(entityId: "entity-antonio")

        state.focusClaim(claimId: "claim-1", sourceDocumentId: "doc-source-1")

        XCTAssertNil(
            state.focusedEntityId,
            "documents the trap: focusClaim's default entityId: nil overwrites an existing focus unconditionally"
        )
        XCTAssertEqual(
            DocumentInspector.inspectorArm(hasDocument: false, focusedEntityId: state.focusedEntityId),
            .empty,
            "documents the symptom: the Inspector arm collapses to .empty once the entity is cleared this way"
        )
    }
}
