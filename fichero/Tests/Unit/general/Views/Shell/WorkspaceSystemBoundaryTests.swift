import XCTest

/// spec: panes-workspaces §"RATIFIED 2026-09-15 — ONE system, enforced by tests"
/// (`workspaces.one-system`). Source guardrails, the `MenuShortcutBoundaryTests` shape: the pane /
/// workspace feature shipped as a half-finished migration with TWO built-in systems (the legacy
/// `BuiltInWorkspace` show/hide presets alongside the `BuiltInWorkspaceLayout` PaneList
/// compositions). They were consolidated to one; these tests fail if the second grows back.
final class WorkspaceSystemBoundaryTests: XCTestCase {

    /// The built-in workspaces are the SIX v2 compositions and ⌘⌥1–6 apply them through the window
    /// command bus (`WorkspaceCommandsSection` → `applyWorkspaceLayout`), using each layout's
    /// `defaultSlot`. One list, one shortcut binding.
    ///
    /// #4968: the built-in list and the apply verb now live in `WorkspacesMenuBody.swift` — the
    /// ONE shared definition `WorkspaceCommandsSection` (the menu bar) and the toolbar's
    /// Workspaces menu both render, so the two cannot list the built-ins differently. The
    /// shortcut MINT stays on `WorkspaceCommandsSection` in `ViewMenuPaneSections.swift`
    /// (`MenuShortcutUniquenessTests` calls it there by name), which is why that file is checked
    /// for the chord assertion below and the shared file for the list/verb ones.
    func testCommandOptionNumbersApplyTheV2Workspaces() throws {
        let sharedBody = try Self.appSource("App/Menus/WorkspacesMenuBody.swift")
        XCTAssertTrue(
            sharedBody.contains("ForEach(BuiltInWorkspaceLayout.allCases)"),
            "The ONE shared Workspaces body iterates the one built-in system (BuiltInWorkspaceLayout).")
        XCTAssertTrue(
            sharedBody.contains("commands?.applyWorkspaceLayout(layout)"),
            "⌘⌥1–6 must apply a v2 workspace via the command bus's applyWorkspaceLayout verb.")

        let shortcutMint = try Self.appSource("App/Menus/ViewMenuPaneSections.swift")
        XCTAssertTrue(
            shortcutMint.contains("modifiers: [.command, .option]"),
            "The workspace slots are ⌘⌥ chords.")
    }

    /// The centre renders through ONE path (`panes.one-renderer`). This used to assert that BOTH
    /// branches of the routing named a renderer — the applied `paneListRow` and a default
    /// `paneComposition`. The second branch was unreachable (`activePaneList` is seeded non-nil and
    /// nothing can clear it) and was deleted with the pre-workspace renderer (#4683), so the
    /// property to guard is now stronger: there is exactly ONE renderer and no fallback to drift
    /// back into.
    func testCentreRoutesThroughTheSinglePaneListRenderer() throws {
        let source = try Self.appSource("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift")
        XCTAssertTrue(
            source.contains("paneListRow(activePaneList)"),
            "The centre renders the stored PaneList through paneListRow — the single renderer.")
    }

    /// The Optional on `activePaneList` was what kept the unreachable branch alive: nothing ever
    /// assigned nil, so `PaneList?` bought only a dead `else`. Non-optional is the invariant
    /// ("a workspace is ALWAYS applied") expressed in the type (#4683).
    /// Checks the NON-OPTIONALITY (the actual invariant, "a workspace is always applied"), not
    /// the literal seed expression — #4686 changed the seed from a bare `BuiltInWorkspaceLayout`
    /// literal to `WorkspaceLayoutDefaults.rememberedPaneList() ?? BuiltInWorkspaceLayout...`
    /// (mirroring how the three legacy Bools are seeded), which is still a non-optional default,
    /// just no longer a single literal.
    func testActivePaneListIsNonOptionalSoThereIsNoFallbackBranch() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView.swift")
        XCTAssertTrue(
            source.contains("var activePaneList: PaneList ="),
            "activePaneList is non-optional — a workspace is always applied.")
        XCTAssertTrue(
            source.contains("BuiltInWorkspaceLayout.read.panes"),
            "The Read default must still be the seed's fallback (spec panes.layout.mail-default).")
    }

    /// BUG2 regression guard (spec panes.close.this-pane-only): in an applied workspace the pane
    /// head's X must remove THIS leaf from the stored PaneList, never the whole row. The wiring is a
    /// `\.paneCloseAction` environment seam — `paneListRow` publishes `removingLeaf(id)` per leaf and
    /// `PaneHead`'s X prefers it. If either half is dropped, close silently reverts to closing the
    /// row. (View wiring isn't unit-runnable; this pins the seam at the source.)
    func testAppliedWorkspaceCloseRemovesOnlyThatLeaf() throws {
        let paneSpec = try Self.appSource("Views/Shell/ContentView/Layout/PaneSpec.swift")
        XCTAssertTrue(
            paneSpec.contains("activePaneList.removingLeaf(id)"),
            "paneListRow must close a pane by removing its leaf from the stored PaneList.")
        XCTAssertTrue(
            paneSpec.contains("PaneCloseAction { closeLeaf(id) }"),
            "paneNodeView must publish the per-leaf close action on the applied path.")

        let paneHead = try Self.appSource("Views/Shell/PaneHead/PaneHead.swift")
        XCTAssertTrue(
            paneHead.contains("@Environment(\\.paneCloseAction)"),
            "PaneHead must read the applied-workspace close action.")
        // The X shows whenever an applied close action is present, and calls it — checked ahead of
        // the split-collapse / legacy onClose (the `if let paneCloseAction { paneCloseAction.run() }`
        // branch is first in the button action).
        XCTAssertTrue(
            // The ladder moved into `showsClose` when it was reordered (dfa937946) so a
            // SOLE pane hides its X. This assertion kept naming the OLD inline literal and
            // was therefore red at HEAD — `gate build` only COMPILES tests, so nothing
            // surfaced it. Assert the real shape.
            paneHead.contains("private var showsClose: Bool"),
            "The head's X must appear when an applied close action is present.")
        XCTAssertTrue(
            paneHead.contains("paneCloseAction.run()"),
            "The head's X must call the applied close action (spec panes.close.this-pane-only).")
    }

    /// BUG3 regression guard (spec panes.split.focused-only): splitting one pane in an applied
    /// workspace must split THAT pane only, and — like close — must do so through the authoritative
    /// `PaneList` model. Close was fixed this way: `paneListRow` publishes `activePaneList?.removingLeaf(id)`
    /// per leaf and `PaneHead` calls it (`\.paneCloseAction`). The SYMMETRIC split verb —
    /// `PaneList.splittingLeaf(id, axis:)` — EXISTS in the model but is wired to NOTHING: no app
    /// source calls it and no `paneSplitAction` seam exists, so an applied-workspace split falls back
    /// to the shared `SplittablePane` @SceneStorage mechanism instead of mutating the stored list.
    /// This FAILS today and passes once split is routed through the model like close is.
    ///
    /// #4685: menu Split now routes through `activePaneList.splittingLeaf(id, axis:)`
    /// (`ContentView+LayoutChooser.swift`'s `splitFocusedLeaf`) instead of the dead
    /// `SplitCommandRouting` slot-id space — the skip this test carried is lifted.
    func testAppliedWorkspaceSplitIsWiredThroughThePaneListModel() throws {
        var callers: [String] = []
        for path in try Self.appSwiftFiles() {
            // The model's own definition file is where `splittingLeaf` is declared; a real WIRING is
            // a caller ANYWHERE else (a menu/pane-head action mutating `activePaneList`).
            guard path != "Models/PaneList.swift" else { continue }
            let source = AppSource.codeOnly(try Self.appSource(path))
            if source.contains("splittingLeaf(") { callers.append(path) }
        }
        XCTAssertFalse(
            callers.isEmpty,
            "PaneList.splittingLeaf is dead — no app code calls it, so an applied-workspace split "
            + "cannot target one pane through the model the way close does (spec panes.split.focused-only). "
            + "Wire it symmetrically to close: a per-leaf `activePaneList.splittingLeaf(id, axis:)` "
            + "seam (a `PaneSplitAction` mirroring `PaneCloseAction`)."
        )
    }

    // MARK: - Source helpers (mirror MenuShortcutBoundaryTests)

    private static func appSwiftFiles() throws -> [String] {
        let root = try AppSource.root().standardizedFileURL
        guard let enumerator = FileManager.default.enumerator(
            at: root, includingPropertiesForKeys: nil
        ) else { return [] }
        var paths: [String] = []
        for case let url as URL in enumerator where url.pathExtension == "swift" {
            let full = url.standardizedFileURL.path
            guard full.hasPrefix(root.path + "/") else { continue }
            paths.append(String(full.dropFirst(root.path.count + 1)))
        }
        XCTAssertFalse(paths.isEmpty, "Could not enumerate the app sources at \(root.path)")
        return paths
    }

    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }
}
