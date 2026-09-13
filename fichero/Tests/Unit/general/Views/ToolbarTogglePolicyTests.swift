@testable import Fichero
import XCTest

/// spec: panes-magnifiers-workspaces `panes.toolbar.toggles-consistent`
/// (the "toolbar pane-toggle icons disappear in some layouts" fix).
///
/// The pane-toggle group and the Workspaces menu used to sit inside one gate
/// (`supportsReadingWorkspace == sidebarMode == .library && !isKGLibrarySelection`),
/// so selecting the Entities/Claims collection hid BOTH — including the Workspaces
/// menu whose own comment says it's "NEVER gated" because it's how every other
/// button comes back. These pin the corrected pure policy: toggles show for any
/// library selection (KG collections included), and the Workspaces menu is gated
/// only on the compact nav flow.
final class ToolbarTogglePolicyTests: XCTestCase {

    /// The function takes NO `isKGLibrarySelection` parameter — that omission IS
    /// the fix. Entities and Claims are both `sidebarMode == .library`, so they
    /// keep the toggles the same as a folder selection.
    func testPaneTogglesShowForAnyLibrarySelection() {
        XCTAssertTrue(ContentView.showsPaneToggles(sidebarMode: .library, compactFlow: false))
    }

    func testPaneTogglesHiddenInCompactFlow() {
        XCTAssertFalse(ContentView.showsPaneToggles(sidebarMode: .library, compactFlow: true))
    }

    func testPaneTogglesHiddenForNonLibraryModes() {
        XCTAssertFalse(ContentView.showsPaneToggles(sidebarMode: .chat, compactFlow: false))
        XCTAssertFalse(ContentView.showsPaneToggles(sidebarMode: .research, compactFlow: false))
    }

    /// The Workspaces menu (recovery path for every other button) is present in
    /// every non-compact case — library, entities, claims, chat, anything — and
    /// hidden only in the compact nav-stack flow.
    func testWorkspacesMenuPresentOutsideCompactAlways() {
        XCTAssertTrue(ContentView.showsWorkspacesMenu(compactFlow: false))
        XCTAssertFalse(ContentView.showsWorkspacesMenu(compactFlow: true))
    }
}
