import XCTest

/// spec: panes-workspaces §"RATIFIED 2026-09-15 — ONE system, enforced by tests"
/// (`workspaces.one-system`). The forbidden-pattern ABSENCE guardrails split out of
/// `WorkspaceSystemBoundaryTests` (#5052): each proves a second system is NOT present anywhere
/// in the app source, which only a source scan can show. The positive wiring checks stay in the
/// original file, where they remain counted as scrape debt.
final class WorkspaceOneSystemGuardrailTests: XCTestCase {

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

    /// The pre-workspace centre renderer, the legacy visibility-plan pane list, the retired
    /// `BuiltInWorkspace` menu list and the Optional `activePaneList` must not return.
    func testNoSecondCentreRendererOrOptionalActivePaneList() throws {
        let centre = try Self.appSource("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift")
        XCTAssertFalse(
            centre.contains("paneComposition("),
            "The pre-workspace renderer is deleted; a second centre renderer must not return.")
        XCTAssertFalse(
            centre.contains("PaneList.forLayout("),
            "The centre must not derive a pane list from the legacy visibility plan.")
        let menuBody = try Self.appSource("App/Menus/WorkspacesMenuBody.swift")
        XCTAssertFalse(
            menuBody.contains("BuiltInWorkspace.allCases"),
            "The menu must not iterate the retired BuiltInWorkspace enum — one built-in list only.")
        let contentView = try Self.appSource("Views/Shell/ContentView/ContentView.swift")
        XCTAssertFalse(
            contentView.contains("var activePaneList: PaneList?"),
            "Re-introducing the Optional re-introduces an unreachable fallback renderer.")
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
            "App/Menus/WorkspacesMenuBody.swift",
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
