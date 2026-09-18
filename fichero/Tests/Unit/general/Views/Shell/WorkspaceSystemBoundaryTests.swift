import XCTest

/// spec: panes-workspaces §"RATIFIED 2026-09-15 — ONE system, enforced by tests"
/// (`workspaces.one-system`). Source guardrails, the `MenuShortcutBoundaryTests` shape: the pane /
/// workspace feature shipped as a half-finished migration with TWO built-in systems (the legacy
/// `BuiltInWorkspace` show/hide presets alongside the `BuiltInWorkspaceLayout` PaneList
/// compositions). They were consolidated to one; these tests fail if the second grows back.
final class WorkspaceSystemBoundaryTests: XCTestCase {

    /// The legacy `BuiltInWorkspace` enum (and its per-window `applyBuiltIn` verb) is DELETED — a
    /// workspace is a `PaneList`, built-in or saved (one model). Its reappearance means two systems.
    func testNoLegacyBuiltInWorkspaceSystem() throws {
        var enumOffenders: [String] = []
        var verbOffenders: [String] = []
        for path in try Self.appSwiftFiles() {
            let source = try Self.appSource(path)
            if source.contains("enum BuiltInWorkspace ")
                || source.contains("enum BuiltInWorkspace:")
                || source.contains("enum BuiltInWorkspace{") {
                enumOffenders.append(path)
            }
            // The retired command-bus verb (distinct from the surviving `applyWorkspaceLayout`).
            if source.contains("applyBuiltIn") { verbOffenders.append(path) }
        }
        XCTAssertEqual(
            enumOffenders, [],
            "The legacy `BuiltInWorkspace` enum was deleted (spec workspaces.one-system); a workspace "
                + "is a `BuiltInWorkspaceLayout` PaneList. Reintroducing it restores the two-system split.")
        XCTAssertEqual(
            verbOffenders, [],
            "The legacy `applyBuiltIn` verb was removed from WindowLayoutCommands; the one built-in "
                + "system applies via `applyWorkspaceLayout`.")
    }

    /// The built-in workspaces are the SIX v2 compositions and ⌘⌥1–6 apply them through the window
    /// command bus (`WorkspaceCommandsSection` → `applyWorkspaceLayout`), using each layout's
    /// `defaultSlot`. One list, one shortcut binding.
    func testCommandOptionNumbersApplyTheV2Workspaces() throws {
        let source = try Self.appSource("App/Menus/ViewMenuPaneSections.swift")
        XCTAssertTrue(
            source.contains("ForEach(BuiltInWorkspaceLayout.allCases)"),
            "The menu-bar Workspaces section iterates the one built-in system (BuiltInWorkspaceLayout).")
        XCTAssertTrue(
            source.contains("commands?.applyWorkspaceLayout(layout)"),
            "⌘⌥1–6 must apply a v2 workspace via the command bus's applyWorkspaceLayout verb.")
        XCTAssertTrue(
            source.contains("modifiers: [.command, .option]"),
            "The workspace slots are ⌘⌥ chords.")
        XCTAssertFalse(
            source.contains("BuiltInWorkspace.allCases"),
            "The menu must not iterate the retired BuiltInWorkspace enum — one built-in list only.")
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
        XCTAssertFalse(
            source.contains("paneComposition("),
            "The pre-workspace renderer is deleted; a second centre renderer must not return.")
        XCTAssertFalse(
            source.contains("PaneList.forLayout("),
            "The centre must not derive a pane list from the legacy visibility plan.")
    }

    /// The Optional on `activePaneList` was what kept the unreachable branch alive: nothing ever
    /// assigned nil, so `PaneList?` bought only a dead `else`. Non-optional is the invariant
    /// ("a workspace is ALWAYS applied") expressed in the type (#4683).
    func testActivePaneListIsNonOptionalSoThereIsNoFallbackBranch() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView.swift")
        XCTAssertTrue(
            source.contains("var activePaneList: PaneList = BuiltInWorkspaceLayout"),
            "activePaneList is non-optional — a workspace is always applied.")
        XCTAssertFalse(
            source.contains("var activePaneList: PaneList?"),
            "Re-introducing the Optional re-introduces an unreachable fallback renderer.")
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
            paneHead.contains("if paneCloseAction != nil || onClose != nil || isInSplit"),
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

    /// BUG5 regression guard (spec workspaces.one-system): "Layouts" and "Workspaces" must not be
    /// TWO parallel built-in arrangement systems. Today the app ships both — the `BuiltInWorkspaceLayout`
    /// PaneList compositions (⌘⌥1–6) AND a separate `WindowLayoutPreset` "Layouts" system that applies
    /// visibility Bools on a NON-PaneList path — and lists them side by side in the same menus. The
    /// legacy `BuiltInWorkspace` enum was already deleted to make one system; `WindowLayoutPreset` is
    /// the surviving parallel one. This FAILS while both are enumerated in the arrangement menus.
    ///
    /// NOTE: the consolidation direction (fold the presets into the one PaneList workspace system) is
    /// the manager's call; this pins only that two built-in arrangement systems must not be presented
    /// in parallel — the invariant the CD's "there should be ONE" ruling states.
    func testNoParallelLayoutPresetSystemBesideWorkspaces() throws {
        let menuFiles = [
            "App/Menus/ViewMenuPaneSections.swift",
            "Views/Shell/ContentView/ContentView+LayoutChooser.swift"
        ]
        for path in menuFiles {
            let source = AppSource.codeOnly(try Self.appSource(path))
            let listsWorkspaces = source.contains("BuiltInWorkspaceLayout.allCases")
            let listsPresets = source.contains("WindowLayoutPreset.allCases")
            XCTAssertFalse(
                listsWorkspaces && listsPresets,
                "\(path) presents BOTH the workspace system (BuiltInWorkspaceLayout) and a parallel "
                + "'Layouts' preset system (WindowLayoutPreset) — the two-systems bug (spec "
                + "workspaces.one-system: there must be ONE built-in arrangement system)."
            )
        }
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
