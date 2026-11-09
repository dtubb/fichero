@testable import Fichero
import Testing

/// The Order list's items on the menu bar and the row menu (Step 1.25): each is offered only when the list
/// can act, and says why when it cannot. What breaks without these: a greyed item with no word, or an item
/// live on a selection it cannot act on.
struct OrderListMenuTests {
    @Test("with nothing to act on every new item is disabled and says what to select")
    func noTarget() {
        #expect(LineVerbs.revealReason(nil) == "Select a segment in the Order list")
        #expect(LineVerbs.moveReason(nil) == "Select a row in a named order")
    }

    @Test("each item is live once the list gives its action, and only that one")
    func live() {
        var target = LineVerbsTarget()
        target.reveal = {}
        #expect(LineVerbs.revealReason(target) == nil)
        #expect(LineVerbs.moveReason(target) != nil)
        target.move = { _ in }
        #expect(LineVerbs.moveReason(target) == nil)
    }
}

/// What a click on a Reader line makes the selection (Step 1.25): Finder's rules over the page's order.
struct ReaderPickTests {
    private let order = ["a", "b", "c", "d", "e"]

    @Test("a plain click is that line alone; ⌘ adds and removes; an id off the page changes nothing")
    func plainAndCommand() {
        #expect(ReaderLines.picked("c", held: ["a", "b"], order: order, command: false, shift: false) == ["c"])
        #expect(ReaderLines.picked("c", held: ["a"], order: order, command: true, shift: false) == ["a", "c"])
        #expect(ReaderLines.picked("a", held: ["a", "c"], order: order, command: true, shift: false) == ["c"])
        #expect(ReaderLines.picked("zz", held: ["a"], order: order, command: true, shift: false) == ["a"])
    }

    @Test("⇧ takes the run from the last picked line either way; with ⌘ it is added to what is held")
    func shiftRuns() {
        #expect(ReaderLines.picked("d", held: ["b"], order: order, command: false, shift: true) == ["b", "c", "d"])
        #expect(ReaderLines.picked("a", held: ["c"], order: order, command: false, shift: true) == ["a", "b", "c"])
        #expect(ReaderLines.picked("d", held: ["a", "c"], order: order, command: true, shift: true) == ["a", "c", "d"])
        #expect(ReaderLines.picked("c", held: [], order: order, command: false, shift: true) == ["c"])
    }
}

/// Correct This Line's picture zoom (Step 1.25): never smaller than the line, never past six times it.
struct CorrectLineZoomTests {
    @Test("a pinch is kept between the line's own size and six times it")
    func clamp() {
        #expect(CorrectLine.zoomed(1, by: -0.5) == 1)
        #expect(CorrectLine.zoomed(1, by: 0.5) == 1.5)
        #expect(CorrectLine.zoomed(5, by: 1) == 6)
    }
}
