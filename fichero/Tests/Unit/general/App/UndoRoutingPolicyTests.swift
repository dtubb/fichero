import XCTest
@testable import Fichero

/// #4354 — ⌘Z must be scoped to the focused editor, not the whole app.
///
/// Pure policy coverage: "who should receive undo, given focus state". The
/// AppKit focus probe (`FocusedTextResponder`) supplies the booleans; the
/// decision itself has no view state and is tested here directly.
final class UndoRoutingPolicyTests: XCTestCase {
    // MARK: - Text editing wins

    func testTypingInAnEditorRoutesUndoToThatEditor() {
        // Mid-sentence, with a library action sitting on the audit log: the
        // typing is undone, the library action is untouched.
        XCTAssertEqual(
            UndoRoutingPolicy.route(
                isTextEditing: true,
                textUndoAvailable: true,
                navigationUndoEnabled: true,
                hasAuditedUndo: true
            ),
            .focusedTextEditor
        )
    }

    func testFocusedEditorWithNothingToUndoDoesNotFallThroughToTheLibrary() {
        // The data-integrity case: an empty typing stack means "nothing to undo
        // here", never "go revert the last move/delete/import".
        XCTAssertEqual(
            UndoRoutingPolicy.route(
                isTextEditing: true,
                textUndoAvailable: false,
                navigationUndoEnabled: true,
                hasAuditedUndo: true
            ),
            .none
        )
    }

    // MARK: - Image editor wins over the app-level stacks

    func testImageEditorWithStepsTakesUndoAheadOfNavigation() {
        // Editing an image: ⌘Z drops the last edit step, never steps back a
        // folder or reverts a library action (Daniel, 2026-08-31).
        XCTAssertEqual(
            UndoRoutingPolicy.route(
                isTextEditing: false,
                textUndoAvailable: false,
                imageEditUndoEnabled: true,
                navigationUndoEnabled: true,
                hasAuditedUndo: true
            ),
            .imageEdit
        )
    }

    func testTypingStillBeatsTheImageEditor() {
        XCTAssertEqual(
            UndoRoutingPolicy.route(
                isTextEditing: true,
                textUndoAvailable: true,
                imageEditUndoEnabled: true,
                navigationUndoEnabled: false,
                hasAuditedUndo: false
            ),
            .focusedTextEditor
        )
    }

    // MARK: - No text focus falls back to the app-level stacks

    func testNoTextFocusPrefersNavigationUndo() {
        XCTAssertEqual(
            UndoRoutingPolicy.route(
                isTextEditing: false,
                textUndoAvailable: false,
                navigationUndoEnabled: true,
                hasAuditedUndo: true
            ),
            .navigation
        )
    }

    func testNoTextFocusAndNoNavigationReachesTheAuditedActionUndo() {
        XCTAssertEqual(
            UndoRoutingPolicy.route(
                isTextEditing: false,
                textUndoAvailable: false,
                navigationUndoEnabled: false,
                hasAuditedUndo: true
            ),
            .auditedAction
        )
    }

    func testNothingFocusedAndNothingRecordedIsNoRoute() {
        XCTAssertEqual(
            UndoRoutingPolicy.route(
                isTextEditing: false,
                textUndoAvailable: false,
                navigationUndoEnabled: false,
                hasAuditedUndo: false
            ),
            .none
        )
    }

    /// A stale `textUndoAvailable` must not matter once focus has left the
    /// editor — the route is decided by focus first.
    func testTextUndoAvailabilityIsIgnoredWhenNoEditorIsFocused() {
        XCTAssertEqual(
            UndoRoutingPolicy.route(
                isTextEditing: false,
                textUndoAvailable: true,
                navigationUndoEnabled: false,
                hasAuditedUndo: true
            ),
            .auditedAction
        )
    }
}
