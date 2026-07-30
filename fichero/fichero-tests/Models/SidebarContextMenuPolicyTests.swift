@testable import Fichero
import XCTest

/// #4275 + #4305 — context-menu policy, pure logic.
///
/// #4275: the sidebar Run Workflow submenu sourced ONLY the row's own
/// library store, so a non-global library whose workflow list was empty
/// (not yet loaded, or load failed) silently offered nothing. The menu now
/// falls back to the global library's list — never silently empty.
///
/// #4305: Show Original in Finder — one shared policy for every surface:
/// local engine + the path resolves on this machine; linked originals get
/// the Finder-alias verb.
final class SidebarContextMenuPolicyTests: XCTestCase {

    // MARK: - #4275 workflow list fallback

    @MainActor
    func testOwnLibraryWorkflowsAreAuthoritativeWhenPresent() {
        let own = [WorkflowSidebarItem(id: "wf-own", name: "Own")]
        let global = [WorkflowSidebarItem(id: "wf-global", name: "Global")]
        XCTAssertEqual(
            SidebarItemRow.contextMenuWorkflows(own: own, global: global).map(\.id),
            ["wf-own"],
            "#3820: the run executes against the row's library, so its own list wins"
        )
    }

    @MainActor
    func testEmptyOwnListFallsBackToGlobalSoMenuIsNeverSilentlyEmpty() {
        let global = [WorkflowSidebarItem(id: "wf-global", name: "Global")]
        XCTAssertEqual(
            SidebarItemRow.contextMenuWorkflows(own: [], global: global).map(\.id),
            ["wf-global"]
        )
    }

    @MainActor
    func testBothEmptyStillHidesTheMenu() {
        XCTAssertTrue(SidebarItemRow.contextMenuWorkflows(own: [], global: []).isEmpty)
    }

    // MARK: - #4305 reveal policy

    func testRevealsWhenEngineLocalAndFileExists() {
        XCTAssertEqual(
            RevealOriginalPolicy.revealablePath(
                path: "/tmp/original.md", engineIsLocal: true, fileExists: { _ in true }
            ),
            "/tmp/original.md"
        )
    }

    func testOmittedWhenEngineIsRemote() {
        XCTAssertNil(
            RevealOriginalPolicy.revealablePath(
                path: "/tmp/original.md", engineIsLocal: false, fileExists: { _ in true }
            ),
            "a remote engine's paths are not paths on this Mac (#1861)"
        )
    }

    func testOmittedWhenOriginalIsMissingLocally() {
        XCTAssertNil(
            RevealOriginalPolicy.revealablePath(
                path: "/tmp/moved-away.md", engineIsLocal: true, fileExists: { _ in false }
            )
        )
    }

    func testOmittedWithNoOrEmptyPath() {
        XCTAssertNil(RevealOriginalPolicy.revealablePath(path: nil, engineIsLocal: true, fileExists: { _ in true }))
        XCTAssertNil(RevealOriginalPolicy.revealablePath(path: "", engineIsLocal: true, fileExists: { _ in true }))
    }

    func testLinkedItemsGetTheFinderAliasVerb() {
        XCTAssertEqual(RevealOriginalPolicy.label(isLinked: true), "Show Original in Finder")
        XCTAssertEqual(RevealOriginalPolicy.label(isLinked: false), "Reveal in Finder")
    }
}
