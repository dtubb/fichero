@testable import Fichero
import SwiftUI
import Testing

/// The Inspector's Order list claims ⌥⌘↑/↓/⇞/⇟ ONLY while it has focus. A `.keyboardShortcut` on a
/// button is window-wide, so with the list showing a selection the keys pressed in the Reader moved
/// the list's row instead of the Reader's caret line. With the list unfocused there is no shortcut,
/// and the key reaches the Reader's page, whose own handler (`lineMoveMessage`, pinned in
/// `test_reader_line_map.py`) turns it into `ReaderLineMove`.
struct ReadingOrderListKeysTests {
    private let keys: [KeyEquivalent] = [.upArrow, .downArrow, .pageUp, .pageDown]

    @Test("unfocused, the list claims none of the four keys")
    func unfocusedClaimsNothing() {
        for key in keys {
            #expect(ReadingOrderListKeys.shortcut(key, listFocused: false) == nil)
        }
    }

    @Test("focused, each key is ⌥⌘ plus that key")
    func focusedClaimsOptionCommand() {
        for key in keys {
            let shortcut = ReadingOrderListKeys.shortcut(key, listFocused: true)
            #expect(shortcut?.key == key)
            #expect(shortcut?.modifiers == [.command, .option])
        }
    }
}
