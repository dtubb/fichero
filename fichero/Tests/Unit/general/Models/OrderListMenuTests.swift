@testable import Fichero
import Testing

/// The Order list's items on the menu bar and the row menu (Step 1.25): each is offered only when the list
/// can act, and says why when it cannot. What breaks without these: a greyed item with no word, or an item
/// live on a selection it cannot act on.
struct OrderListMenuTests {
    @Test("with nothing to act on every new item is disabled and says what to select")
    func noTarget() {
        #expect(LineVerbs.renameReason(nil) == "Select one line in the Order list")
        #expect(LineVerbs.revealReason(nil) == "Select a segment in the Order list")
        #expect(LineVerbs.moveReason(nil) == "Select a row in a named order")
    }

    @Test("each item is live once the list gives its action, and only that one")
    func live() {
        var target = LineVerbsTarget()
        target.reveal = {}
        #expect(LineVerbs.revealReason(target) == nil)
        #expect(LineVerbs.renameReason(target) != nil)
        #expect(LineVerbs.moveReason(target) != nil)
        target.rename = {}
        target.move = { _ in }
        #expect(LineVerbs.renameReason(target) == nil)
        #expect(LineVerbs.moveReason(target) == nil)
    }
}
