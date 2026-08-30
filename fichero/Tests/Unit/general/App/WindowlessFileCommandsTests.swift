@testable import Fichero
import XCTest

/// #4530 — "New Library doesn't work" and "no way to make a new window when no
/// library is open" were the SAME defect, seen from two sides.
///
/// Every File-menu library/window command read a `@FocusedValue` that only a
/// key `LibraryWindow` supplies via `.focusedSceneValue`, and then wrote
/// `.disabled(action == nil)`. A focused SCENE value is nil whenever no such
/// scene is key — with every window closed, and also while Settings, Activity,
/// About, or the Feature Tier Legend is frontmost. So New Library…, Open…, and
/// New Window all went dead precisely in the states where the user needed them,
/// and New Window — the command whose entire job is to get a window back — was
/// disabled exactly when there were none.
///
/// These are source-shape guards rather than behavioral ones because the defect
/// lives in the menu's DECLARATION: `.disabled(newWindowAction == nil)` is not
/// observable from a unit test without a live scene graph, but it is exactly
/// what must never come back. The panel/naming logic that a test *can* execute
/// is covered in `NewLibraryPanelTests`.
@MainActor
final class WindowlessFileCommandsTests: XCTestCase {

    /// #4493: routed through the shared `AppSource` walk instead of
    /// counting `deletingLastPathComponent()` calls. Counting is correct
    /// only for this file's CURRENT depth — move the file and it resolves
    /// somewhere else and fails later as an unrelated file-not-found.
    private static func appSource(_ relativePath: String) throws -> String {
        let source = try AppSource.text(relativePath)
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    /// The regression itself: no File-menu command may be disabled merely
    /// because no window is key. `supportsMultipleWindows` is the one
    /// legitimate gate — that is a platform fact, not a focus state.
    func testNoFileCommandIsGatedOnAFocusedSceneValueBeingPresent() throws {
        let source = try Self.appSource("App/Menus/FileMenuCommands.swift")

        for action in ["newLibraryAction", "openLibraryAction", "newWindowAction"] {
            XCTAssertFalse(
                source.contains(".disabled(\(action) == nil)"),
                """
                \(action) is gated on a focused scene value again (#4530). \
                With no window key that value is nil, so this disables the \
                command in the exact state it exists to recover from.
                """
            )
        }
    }

    /// Each of the three commands must have an app-scoped path that does not
    /// need a key window. Asserted per-command so fixing one and forgetting
    /// the others cannot pass.
    func testEachWindowlessCommandHasAnAppScopedFallback() throws {
        let source = try Self.appSource("App/Menus/FileMenuCommands.swift")

        XCTAssertTrue(
            source.contains("createLibraryAtAppScope()"),
            "New Library… has no windowless fallback (#4530)"
        )
        XCTAssertTrue(
            source.contains("openLibraryAtAppScope()"),
            "Open… has no windowless fallback (#4530)"
        )
        XCTAssertTrue(
            source.contains("openWindow(id: \"main\")"),
            "New Window has no windowless fallback (#4530)"
        )
    }

    /// The window-scoped action stays PREFERRED where it exists: New Library…
    /// creates in place rather than opening a window (#4062), so the fallback
    /// must be the else-branch, never the only branch.
    func testWindowScopedActionIsStillPreferredWhenPresent() throws {
        let source = try Self.appSource("App/Menus/FileMenuCommands.swift")

        XCTAssertTrue(
            source.contains("if let newLibraryAction {"),
            "New Library… must still prefer the in-place window action (#4062)"
        )
        XCTAssertTrue(
            source.contains("if let newWindowAction {"),
            "New Window must still prefer the window-scoped action when a window is key"
        )
    }

    /// Dock-icon click with no windows. AppKit's default handling creates an
    /// untitled DOCUMENT, which a non-document-based app has none of — so the
    /// delegate must handle reopen itself, and the documented way to say "I
    /// handled it" is returning false.
    func testDelegateHandlesReopenWithNoVisibleWindows() throws {
        let source = try Self.appSource("FicheroApp.swift")

        XCTAssertTrue(
            source.contains("func applicationShouldHandleReopen("),
            "No reopen handler — a Dock click with every window closed does nothing (#4530)"
        )
        XCTAssertTrue(
            source.contains("guard !hasVisibleWindows, let openMainWindow else { return true }"),
            """
            The reopen handler must defer to AppKit (return true) when windows \
            already exist or when no openWindow action has been captured — \
            returning false there suppresses the default in exchange for nothing.
            """
        )
    }

    /// The captured action is what makes the handler work; without the install
    /// site the guard above always takes the `return true` path and the fix is
    /// silently inert.
    func testOpenWindowActionIsInstalledOnTheDelegate() throws {
        let source = try Self.appSource("FicheroApp.swift")

        XCTAssertTrue(
            source.contains("appDelegate.openMainWindow = { openWindow(id: \"main\") }"),
            "openMainWindow is never installed, so applicationShouldHandleReopen can never fire (#4530)"
        )
    }
}
