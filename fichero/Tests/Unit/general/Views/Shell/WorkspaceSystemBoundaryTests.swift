import XCTest

/// spec: panes-magnifiers-workspaces §"RATIFIED 2026-09-15 — ONE system, enforced by tests"
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

    /// The centre renders through ONE path (`panes.one-renderer`): an applied workspace draws via
    /// `paneListRow`/`paneComposition` over a `PaneList`, never a resurrected per-mode raw renderer
    /// in the routing. Guards the routing file names the single path.
    func testCentreRoutesThroughTheSinglePaneListRenderer() throws {
        let source = try Self.appSource("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift")
        XCTAssertTrue(
            source.contains("paneListRow(applied)"),
            "An applied workspace renders through paneListRow (the single PaneList renderer).")
        XCTAssertTrue(
            source.contains("paneComposition(list)"),
            "The default centre renders through paneComposition — the same one renderer.")
    }

    /// BUG2 regression guard (spec panes.close.this-pane-only): in an applied workspace the pane
    /// head's X must remove THIS leaf from the stored PaneList, never the whole row. The wiring is a
    /// `\.paneCloseAction` environment seam — `paneListRow` publishes `removingLeaf(id)` per leaf and
    /// `PaneHead`'s X prefers it. If either half is dropped, close silently reverts to closing the
    /// row. (View wiring isn't unit-runnable; this pins the seam at the source.)
    func testAppliedWorkspaceCloseRemovesOnlyThatLeaf() throws {
        let paneSpec = try Self.appSource("Views/Shell/ContentView/Layout/PaneSpec.swift")
        XCTAssertTrue(
            paneSpec.contains("activePaneList?.removingLeaf(id)"),
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
