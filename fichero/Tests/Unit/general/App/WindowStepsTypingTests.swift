#if os(macOS)
import AppKit
@testable import Fichero
import XCTest

/// `undo.window.own-stack` (#5658): typing in a field and a person's project steps never share a stack. A
/// real window with a real text view: the field's typing undo lives on the manager AppKit gives the text
/// view, and the window's steps live on their own; ⌘Z while typing undoes only the typing, and taking a
/// step back never touches the typing. What breaks without it: ⌘Z in a field pops a delete made a minute
/// ago, or a step's undo swallows the sentence being typed.
@MainActor
final class WindowStepsTypingTests: XCTestCase {
    @MainActor
    private final class Engine: UndoSetEngine {
        var projectPath: String? { "/tmp/P.fichero" }
        var sets: [[String]] = []
        func undoSet(auditIds: [String]) async throws -> [String] {
            sets.append(auditIds)
            return ["u1"]
        }
    }

    private func window(typing text: String) -> (NSWindow, NSTextView) {
        let window = NSWindow(contentRect: CGRect(x: 0, y: 0, width: 400, height: 200),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let textView = NSTextView(frame: CGRect(x: 0, y: 0, width: 400, height: 200))
        textView.isEditable = true
        textView.allowsUndo = true
        window.contentView = textView
        window.makeFirstResponder(textView)
        textView.insertText(text, replacementRange: NSRange(location: 0, length: 0))
        textView.breakUndoCoalescing()
        // The typing group closes at the end of the event, as it does when a person types.
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        return (window, textView)
    }

    func testTypingAndTheWindowsStepsAreTwoStacks() throws {
        let steps = WindowSteps()
        steps.register(["a1"], named: "Move to Trash", engine: Engine())
        let (window, textView) = window(typing: "Juan de la Cruz")
        defer { window.close() }

        let typing = try XCTUnwrap(textView.undoManager, "the text view has its typing stack")
        XCTAssertFalse(typing === steps.undoManager, "typing and project steps never share a stack")
        XCTAssertTrue(typing.canUndo, "the typing can be undone")
        XCTAssertTrue(steps.canUndo)
        XCTAssertEqual(steps.undoName, "Move to Trash")
    }

    func testUndoingTypingNeverPopsAProjectStep() throws {
        let steps = WindowSteps()
        let engine = Engine()
        steps.register(["a1"], named: "Move to Trash", engine: engine)
        let (window, textView) = window(typing: "Juan de la Cruz")
        defer { window.close() }

        try XCTUnwrap(textView.undoManager).undo()
        XCTAssertEqual(textView.string, "", "the typing is gone")
        XCTAssertTrue(steps.canUndo, "the step is still offered")
        XCTAssertEqual(steps.undoName, "Move to Trash")
        XCTAssertTrue(engine.sets.isEmpty, "and the engine was asked nothing")
    }

    func testTakingAStepBackNeverTouchesTheTyping() async throws {
        let steps = WindowSteps()
        let engine = Engine()
        steps.register(["a1"], named: "Move to Trash", engine: engine)
        let (window, textView) = window(typing: "Juan de la Cruz")
        defer { window.close() }

        steps.undo()
        for _ in 0..<200 where steps.inFlight > 0 { try await Task.sleep(nanoseconds: 2_000_000) }
        XCTAssertEqual(engine.sets, [["a1"]])
        XCTAssertEqual(textView.string, "Juan de la Cruz", "the sentence being typed is untouched")
        XCTAssertTrue(try XCTUnwrap(textView.undoManager).canUndo, "and its typing can still be undone")
    }

    /// With a field focused, the Edit menu's ⌘Z is the field's (or nothing), never the window's step.
    func testTheMenuRoutesTypingFirst() {
        XCTAssertEqual(
            UndoRoutingPolicy.route(isTextEditing: true, textUndoAvailable: false, windowUndoAvailable: true), .none
        )
        XCTAssertEqual(
            UndoRoutingPolicy.route(isTextEditing: false, textUndoAvailable: false, windowUndoAvailable: true),
            .windowStep
        )
    }
}
#endif
