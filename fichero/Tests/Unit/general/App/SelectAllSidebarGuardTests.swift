@testable import Fichero
import Foundation
import Testing

/// ⌘A never selects the whole sidebar (`ui.select-all.never-the-sidebar`, #6364): when the sidebar
/// outline holds the keyboard, the route takes ⌘A and ignores it, whatever the tap-based pane hint
/// says, so the system's Select All never reaches the outline.
@Suite("Select All is refused while the sidebar holds the keyboard")
struct SelectAllSidebarGuardTests {

    @Test("the sidebar holding the keyboard wins over any pane hint")
    func sidebarFocusWins() {
        #expect(SelectAllSidebarGuard.surface(sidebarHoldsKeyboardFocus: true, paneSurface: .libraryRows) == .sidebar)
        #expect(SelectAllSidebarGuard.surface(sidebarHoldsKeyboardFocus: true, paneSurface: nil) == .sidebar)
        #expect(SelectAllRoutingPolicy.route(isTextEditing: false, focusedSurface: .sidebar) == .sidebarIgnored)
    }

    @Test("without the sidebar, the pane hint decides as before")
    func paneHintOtherwise() {
        #expect(SelectAllSidebarGuard.surface(sidebarHoldsKeyboardFocus: false, paneSurface: .libraryRows) == .libraryRows)
        #expect(SelectAllSidebarGuard.surface(sidebarHoldsKeyboardFocus: false, paneSurface: nil) == nil)
    }

    @Test("a rename field in the sidebar still gets ⌘A for its text")
    func textEditingStillWins() {
        #expect(SelectAllRoutingPolicy.route(isTextEditing: true, focusedSurface: .sidebar) == .focusedTextEditor)
    }
}
