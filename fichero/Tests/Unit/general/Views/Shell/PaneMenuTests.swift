@testable import Fichero
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/panes-workspaces.md -- `panes.chrome.one-pane-menu`. The pane menu's button is
/// the pane's own icon with a chevron, never a +; the menu offers Focus on Pane for the pane it is chosen on, and Leave
/// Focus while that pane is in Focus. What breaks without these: a + that reads as "add", or a Focus entry that names
/// the wrong pane.
@MainActor
struct PaneMenuTests {
    @Test("the button wears the pane's kind icon, never a +")
    func buttonIcon() {
        for kind in PaneSpec.Kind.selectableKinds {
            #expect(PaneMenuEntries.buttonIcon(kind) == kind.icon)
            #expect(PaneMenuEntries.buttonIcon(kind) != "plus")
        }
        #expect(PaneMenuEntries.buttonIcon(nil) != "plus")
    }

    @Test("Focus on Pane for the pane chosen on; Leave Focus while that very pane is in Focus")
    func focusEntry() {
        let mine = UUID(), other = UUID()
        #expect(PaneMenuEntries.focusTitle(leaf: mine, focused: nil) == "Focus on Pane")
        #expect(PaneMenuEntries.focusTitle(leaf: mine, focused: mine) == "Leave Focus")
        #expect(PaneMenuEntries.focusTitle(leaf: mine, focused: other) == "Focus on Pane")
        #expect(PaneMenuEntries.focusTitle(leaf: nil, focused: nil) == "Focus on Pane")
    }
}
