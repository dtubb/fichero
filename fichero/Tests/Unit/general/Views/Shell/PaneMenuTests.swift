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

    @Test("the head has no pin button; the menu's Pin Pane is a toggle, checked while pinned (#6741)")
    func pinLivesInTheMenu() throws {
        let head = try AppSource.code("Views/Shell/PaneHead/PaneHead.swift")
        let menu = try AppSource.code("Views/Shell/PaneHead/PaneChromeMenu.swift")
        #expect(!head.contains("pinToggle"), "the head still places its own pin button")
        #expect(!head.contains("paneHeadPinToggle"))
        #expect(menu.contains("Toggle(isOn: isPinned)"), "Pin Pane is not a checked toggle")
        #expect(menu.contains("Label(\"Pin Pane\", systemImage: \"pin\")"))
        #expect(!menu.contains("\"Unpin Pane\""), "a checked toggle needs no second title")
    }
}
