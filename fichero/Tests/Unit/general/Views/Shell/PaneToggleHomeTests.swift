@testable import Fichero
import Testing

/// Show/Hide Items, Source and Reader are a toolbar group on the Mac and the Workspaces menu's first section on the
/// iPad and iPhone (`shell.toolbar.ipad-matches-the-mac`, #6563).
struct PaneToggleHomeTests {
    @Test func theMacKeepsTheToolbarGroup() {
        #expect(PaneToggleHome.home(isIOS: false) == .toolbarGroup)
    }

    @Test func iOSPutsThemInTheWorkspacesMenu() {
        #expect(PaneToggleHome.home(isIOS: true) == .workspacesMenu)
    }
}
