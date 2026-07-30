import XCTest

final class MenuShortcutBoundaryTests: XCTestCase {
    func testViewMenuAvoidsImportAndSearchShortcutCollisions() throws {
        // #4024: pane-visibility keyboard shortcuts moved to ViewMenuPaneSections.swift.
        let source = try Self.appSource("App/Menus/ViewMenuPaneSections.swift")
        XCTAssertTrue(source.contains(".keyboardShortcut(\"i\", modifiers: [.command, .control])"))
        XCTAssertFalse(source.contains(".keyboardShortcut(\"i\", modifiers: [.command, .option])"))
        XCTAssertTrue(source.contains(".keyboardShortcut(\"f\", modifiers: [.command, .option])"))
        XCTAssertFalse(source.contains(".keyboardShortcut(\"f\", modifiers: .command)"))
    }

    /// #4354 — exactly ONE ⌘Z key equivalent may exist in the app, and it must
    /// defer to the focused text editor before doing anything app-level.
    ///
    /// A `.keyboardShortcut("z", modifiers: .command)` on a menu item becomes an
    /// NSMenuItem key equivalent, which AppKit matches BEFORE the key event
    /// reaches the responder chain. A second one, or one that skips the routing
    /// policy, silently reverts an unrelated move/delete/workflow result while
    /// the user is typing.
    func testOnlyUndoCommandRegistersCommandZAndItDefersToTheResponderChain() throws {
        let owner = "App/Menus/FocusedCommandButtons+UndoNavigation.swift"
        var offenders: [String] = []
        for path in try Self.appSwiftFiles() where path != owner {
            let source = try Self.appSource(path)
            if source.contains("keyboardShortcut(\"z\"") || source.contains("keyboardShortcut(\"Z\"") {
                offenders.append(path)
            }
        }
        XCTAssertEqual(
            offenders, [],
            "⌘Z must be registered in exactly one place (\(owner)); a second key equivalent "
                + "intercepts typing ahead of the responder chain (#4354)."
        )

        let undoSource = try Self.appSource(owner)
        XCTAssertTrue(undoSource.contains("keyboardShortcut(\"z\", modifiers: .command)"))
        XCTAssertTrue(
            undoSource.contains("UndoRoutingPolicy.route("),
            "The ⌘Z command must consult UndoRoutingPolicy before acting (#4354)."
        )
        XCTAssertTrue(
            undoSource.contains("FocusedTextResponder.undo()"),
            "The ⌘Z command must hand undo back to the focused text editor (#4354)."
        )
    }

    /// #4376 — exactly ONE ⌘A MENU key equivalent may exist, and it must consult
    /// the focus routing policy before acting.
    ///
    /// Scoped to `App/Menus/**` deliberately: the hazard #4354 documents is
    /// specifically the NSMenuItem key equivalent, which AppKit matches ahead of
    /// the responder chain. View-level `.keyboardShortcut` on an ordinary Button
    /// is matched later and is a different (lesser) problem — see the reported
    /// second ⌘A binding in `Views/Chat/Inspector/ChatInspector+Header.swift`,
    /// which this lane did not route.
    func testOnlySelectAllCommandRegistersCommandAInTheMenus() throws {
        let owner = "App/Menus/FocusedCommandButtons+SelectAll.swift"
        var offenders: [String] = []
        for path in try Self.appSwiftFiles()
        where path != owner && path.hasPrefix("App/Menus/") {
            let source = try Self.appSource(path)
            if source.contains("keyboardShortcut(\"a\"") || source.contains("keyboardShortcut(\"A\"") {
                offenders.append(path)
            }
        }
        XCTAssertEqual(
            offenders, [],
            "⌘A must be registered in exactly one menu command (\(owner)); a second key "
                + "equivalent intercepts the focused surface ahead of the responder chain (#4376)."
        )

        let source = try Self.appSource(owner)
        XCTAssertTrue(source.contains("keyboardShortcut(\"a\", modifiers: .command)"))
        XCTAssertTrue(
            source.contains("SelectAllRoutingPolicy.route("),
            "The ⌘A command must consult SelectAllRoutingPolicy before acting (#4376)."
        )
        XCTAssertTrue(
            source.contains("FocusedTextResponder.selectAll()"),
            "The ⌘A command must hand select-all back to the focused text editor (#4376)."
        )
        XCTAssertTrue(
            source.contains("FocusedTextResponder.isEditing"),
            "⌘A must reuse #4354's focus probe, not a second focus-detection scheme (#4376)."
        )
        XCTAssertTrue(
            source.contains(".disabled(route == .none)"),
            "⌘A must DISABLE itself when the app has no claim, so the reader's WebKit "
                + "surface still receives it through the responder chain (#4376)."
        )
    }

    /// The Edit menu must actually host the routed Select All — a policy nobody
    /// mounts is the bug #4376 started from (a published `librarySelectAll`
    /// focused action with no consumer).
    func testEditMenuHostsTheRoutedSelectAll() throws {
        let source = try Self.appSource("FicheroApp.swift")
        XCTAssertTrue(source.contains("SelectAllButton()"))
        XCTAssertTrue(
            source.contains("CommandGroup(after: .pasteboard)"),
            "Select All is added after the system pasteboard group; replacing that group "
                + "would take over Cut/Copy/Paste too (#4376)."
        )
    }

    /// The Edit menu still replaces `.undoRedo` (one Undo item, not two) — the
    /// fix is the route inside it, not removing the replacement.
    func testEditMenuStillReplacesUndoRedoWithASingleUndoItem() throws {
        let source = try Self.appSource("FicheroApp.swift")
        XCTAssertTrue(source.contains("CommandGroup(replacing: .undoRedo)"))
        XCTAssertTrue(source.contains("UndoLastActionButton()"))
    }

    /// Every `.swift` path under the app target, relative to `fichero/fichero/`.
    private static func appSwiftFiles() throws -> [String] {
        let root = Self.appRoot.standardizedFileURL
        guard let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: nil
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

    private static var appRoot: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
    }

    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: appRoot.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
