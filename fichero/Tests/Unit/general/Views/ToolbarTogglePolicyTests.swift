@testable import Fichero
import XCTest

/// spec: panes-workspaces `panes.toolbar.toggles-consistent`
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

    /// #4705 "4a-follow" (#4779): exhaustive per-`SidebarMode`, every mode
    /// whose centre content is now pane-hosted (`.library`, `.chat`,
    /// `.workflows`, `.automation`, `.activity`) shows the toggles; only
    /// `.research` — still a bespoke takeover — hides them. Superseded
    /// `testPaneTogglesHiddenForNonLibraryModes`, which asserted `.chat`
    /// hides the toggles — true before 2026-08-12's "chat no longer takes
    /// over" fix made that assertion stale (the toggles just weren't wired
    /// to say so until now).
    func testPaneTogglesShowForEveryPaneHostedModeHideOnlyForResearch() {
        for mode in SidebarMode.allCases {
            let expected = mode != .research
            XCTAssertEqual(
                ContentView.showsPaneToggles(sidebarMode: mode, compactFlow: false),
                expected,
                "\(mode)"
            )
        }
    }

    /// Every mode hides the toggles in the compact nav-stack flow, regardless
    /// of whether it is pane-hosted at regular width.
    func testPaneTogglesHiddenInCompactFlowForEveryMode() {
        for mode in SidebarMode.allCases {
            XCTAssertFalse(ContentView.showsPaneToggles(sidebarMode: mode, compactFlow: true), "\(mode)")
        }
    }

    /// The Workspaces menu (recovery path for every other button) is present in
    /// every non-compact case — library, entities, claims, chat, anything — and
    /// hidden only in the compact nav-stack flow.
    func testWorkspacesMenuPresentOutsideCompactAlways() {
        XCTAssertTrue(ContentView.showsWorkspacesMenu(compactFlow: false))
        XCTAssertFalse(ContentView.showsWorkspacesMenu(compactFlow: true))
    }

    /// #4834: `isTakeoverMode` was extracted out of `showsPaneToggles` so a
    /// second call site (the claim-source reveal's mode-switch guard) shares
    /// the SAME source of truth instead of a hand-listed duplicate. This
    /// pins it to exactly `.research` — it must fail loudly, not silently
    /// pass a wider surface through, the day the last takeover retires.
    func testIsTakeoverModeIsExactlyResearch() {
        for mode in SidebarMode.allCases {
            XCTAssertEqual(ContentView.isTakeoverMode(mode), mode == .research, "\(mode)")
        }
    }
}
