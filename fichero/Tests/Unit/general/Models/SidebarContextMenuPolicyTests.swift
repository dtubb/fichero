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
        let global = [WorkflowSidebarItem(id: "wf-global", name: "Global", isSystem: true)]
        XCTAssertEqual(
            SidebarItemRow.contextMenuWorkflows(own: [], global: global).map(\.id),
            ["wf-global"]
        )
    }

    @MainActor
    func testBothEmptyStillHidesTheMenu() {
        XCTAssertTrue(SidebarItemRow.contextMenuWorkflows(own: [], global: []).isEmpty)
    }

    // MARK: - #4450 the fallback offers only what the engine will resolve

    /// A global-library USER workflow — one built while Global was open, or a
    /// preset demoted by editing it (#780) — is not a default.
    /// `resolve_default_workflow` refuses it from another library, so the
    /// menu offering it produced "Workflow not found in this library: …".
    @MainActor
    func testGlobalFallbackOffersOnlySystemDefaults() {
        let global = [
            WorkflowSidebarItem(id: "wf-preset", name: "Transcribe", isSystem: true),
            WorkflowSidebarItem(id: "wf-user", name: "Daniel's thing", isSystem: false)
        ]
        XCTAssertEqual(
            SidebarItemRow.contextMenuWorkflows(own: [], global: global).map(\.id),
            ["wf-preset"],
            "every offered item must be one the engine can resolve cross-library"
        )
    }

    @MainActor
    func testFallbackOfOnlyUserWorkflowsOffersNothingRatherThanSomethingBroken() {
        let global = [WorkflowSidebarItem(id: "wf-user", name: "Mine", isSystem: false)]
        XCTAssertTrue(SidebarItemRow.contextMenuWorkflows(own: [], global: global).isEmpty)
    }

    // MARK: - #4450 two groups, from one list

    /// The library's own `/api/workflows` ALREADY merges the shipped defaults
    /// in server-side (workflows.py:884), so the split is `isSystem` over one
    /// list — reading the global store again here would list every default
    /// twice.
    @MainActor
    func testMenuSplitsIntoGlobalDefaultsAndThisLibrarysOwn() {
        let merged = [
            WorkflowSidebarItem(id: "wf-preset", name: "Transcribe", isSystem: true),
            WorkflowSidebarItem(id: "wf-mine", name: "Marshall pass", isSystem: false),
            WorkflowSidebarItem(id: "wf-preset-2", name: "Catalogue", isSystem: true)
        ]
        let sections = SidebarItemRow.workflowMenuSections(merged)
        XCTAssertEqual(sections.defaults.map(\.id), ["wf-preset", "wf-preset-2"])
        XCTAssertEqual(sections.libraryOwn.map(\.id), ["wf-mine"])
    }

    @MainActor
    func testEveryOfferedWorkflowLandsInExactlyOneSection() {
        let merged = [
            WorkflowSidebarItem(id: "a", name: "A", isSystem: true),
            WorkflowSidebarItem(id: "b", name: "B", isSystem: false)
        ]
        let sections = SidebarItemRow.workflowMenuSections(merged)
        let ids = sections.defaults.map(\.id) + sections.libraryOwn.map(\.id)
        XCTAssertEqual(ids.sorted(), ["a", "b"], "no workflow may be dropped or listed twice")
    }

    @MainActor
    func testALibraryWithOnlyDefaultsShowsJustTheDefaultsSection() {
        let sections = SidebarItemRow.workflowMenuSections(
            [WorkflowSidebarItem(id: "a", name: "A", isSystem: true)]
        )
        XCTAssertTrue(sections.libraryOwn.isEmpty)
        XCTAssertFalse(sections.defaults.isEmpty, "global defaults are visible in EVERY library")
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
