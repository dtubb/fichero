import XCTest
@testable import Fichero

/// #4354, #5658 — ⌘Z is scoped to what has focus, then to THIS window's steps, and nothing else.
///
/// Pure policy coverage: "who should receive undo, given focus state". The
/// AppKit focus probe (`FocusedTextResponder`) supplies the booleans; the
/// decision itself has no view state and is tested here directly.
final class UndoRoutingPolicyTests: XCTestCase {
    // MARK: - Text editing wins

    func testTypingInAnEditorRoutesUndoToThatEditor() {
        // Mid-sentence, with a step on the window's stack: the typing is undone, the step is untouched.
        XCTAssertEqual(
            UndoRoutingPolicy.route(isTextEditing: true, textUndoAvailable: true, windowUndoAvailable: true),
            .focusedTextEditor
        )
    }

    func testFocusedEditorWithNothingToUndoDoesNotFallThroughToTheWindowsSteps() {
        // The data-integrity case: an empty typing stack means "nothing to undo
        // here", never "go revert the last move/delete/import".
        XCTAssertEqual(
            UndoRoutingPolicy.route(isTextEditing: true, textUndoAvailable: false, windowUndoAvailable: true),
            .none
        )
    }

    // MARK: - Image editor wins over the window's steps

    func testImageEditorWithStepsTakesUndoAheadOfTheWindowsSteps() {
        XCTAssertEqual(
            UndoRoutingPolicy.route(
                isTextEditing: false, textUndoAvailable: false, imageEditUndoEnabled: true, windowUndoAvailable: true
            ),
            .imageEdit
        )
    }

    func testTypingStillBeatsTheImageEditor() {
        XCTAssertEqual(
            UndoRoutingPolicy.route(isTextEditing: true, textUndoAvailable: true, imageEditUndoEnabled: true),
            .focusedTextEditor
        )
    }

    // MARK: - The window's own steps (#5658, undo.window)

    func testAStepTakenInThisWindowIsWhatUndoReaches() {
        XCTAssertEqual(
            UndoRoutingPolicy.route(isTextEditing: false, textUndoAvailable: false, windowUndoAvailable: true),
            .windowStep
        )
    }

    /// `undo.window`, `undo.edit-menu.never-navigates`: with nothing made in this window, Undo is
    /// disabled, whatever the project's history holds and whatever Back could do.
    func testNothingMadeInThisWindowIsNoRoute() {
        XCTAssertEqual(
            UndoRoutingPolicy.route(isTextEditing: false, textUndoAvailable: false, windowUndoAvailable: false),
            .none
        )
    }

    /// A stale `textUndoAvailable` must not matter once focus has left the editor.
    func testTextUndoAvailabilityIsIgnoredWhenNoEditorIsFocused() {
        XCTAssertEqual(
            UndoRoutingPolicy.route(isTextEditing: false, textUndoAvailable: true, windowUndoAvailable: false),
            .none
        )
    }

    func testRedoPutsBackThisWindowsStepAndTypingComesFirst() {
        XCTAssertEqual(
            RedoRoutingPolicy.route(isTextEditing: false, textRedoAvailable: false, windowRedoAvailable: true),
            .windowStep
        )
        XCTAssertEqual(
            RedoRoutingPolicy.route(isTextEditing: true, textRedoAvailable: false, windowRedoAvailable: true),
            .none
        )
        XCTAssertEqual(
            RedoRoutingPolicy.route(isTextEditing: false, textRedoAvailable: false, windowRedoAvailable: false),
            .none
        )
    }

    @MainActor
    func testAStepRegisteredOnTheWindowsStepsIsWhatTheMenuReaches() {
        // The stack the menu reads is the one the helper registers on; its name is the step's.
        let steps = WindowSteps()
        steps.register(["a1"], named: "Merge", engine: NoEngine())
        XCTAssertTrue(steps.canUndo)
        XCTAssertEqual(steps.undoName, "Merge")
    }

    @MainActor
    private final class NoEngine: UndoSetEngine {
        var projectPath: String? { "/tmp/P.fichero" }
        func undoSet(auditIds: [String]) async throws -> [String] { auditIds }
    }
}
