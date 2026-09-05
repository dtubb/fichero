@testable import Fichero
import XCTest

/// Source-surface tests for #4452 — the Data-menu Import… item is dead
/// while the library content pane (not the sidebar) has focus.
///
/// The trap named in #4449's own commit message: `SidebarActions` is an
/// 11-closure bundle (rename/delete/chat/workflow/schedule/trigger/…), and
/// LibraryView has no honest implementation for most of them. Publishing
/// `SidebarActions` from LibraryView with the rest stubbed as no-ops would
/// silently ENABLE those Data-menu items while doing nothing — a new
/// instance of the exact silent-failure bug #4449 closed, just one level
/// up. The fix is a narrower FocusedValue key carrying ONLY what
/// LibraryView really implements (import), so `impossible > checked`:
/// a menu item this pane cannot honor stays disabled, never wired to a
/// no-op.
final class LibraryImportFocusedValueTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testLibraryImportActionKeyIsNarrowNotSidebarActions() throws {
        let source = try Self.appSource("App/Menus/FocusedCommands/FocusedCommandButtons+FocusedValues.swift")
        XCTAssertTrue(source.contains("struct LibraryImportActionKey: FocusedValueKey"))
        // The Value is the Equatable wrapper, NEVER a raw closure (Daniel,
        // 2026-08-29): a raw `(IngestMode) -> Void` re-published every body
        // pass and the invalidation storm hung the iPhone's navigation pop.
        XCTAssertTrue(source.contains("typealias Value = FocusedLibraryImportAction"))
        XCTAssertFalse(source.contains("typealias Value = (IngestMode) -> Void"))
        XCTAssertTrue(source.contains("var libraryImportAction: LibraryImportActionKey.Value?"))
    }

    func testLibraryImportActionIsEquatableAndStableAcrossInstances() {
        // The whole point of the wrapper: two instances built on different
        // body passes must compare EQUAL so the focus system short-circuits
        // the republish (the SidebarActions pattern). If this ever fails,
        // the per-frame republish storm — and the iPhone back-stall — is back.
        let first = FocusedLibraryImportAction { _ in }
        let second = FocusedLibraryImportAction { _ in }
        XCTAssertEqual(first, second)
    }

    func testLibraryViewPublishesItsOwnImportActionWhenFocused() throws {
        // LibraryView.swift was split 2026-08-13; scan all four parts.
        let source = try [
            "Views/Library/LibraryView.swift",
            "Views/Library/LibraryView+Body.swift",
            "Views/Library/LibraryView+ContentBranches.swift",
            "Views/Library/LibraryView+Insets.swift"
        ].map(Self.appSource).joined()
        XCTAssertTrue(source.contains(".focusedValue(\\.libraryImportAction, FocusedLibraryImportAction {"))
        // States mode + target before presenting — same discipline as the
        // other three surfaces (#4449).
        XCTAssertTrue(source.contains("fileImportMode = mode"))
        XCTAssertTrue(source.contains("fileImportTargetFolderId = folderId"))
        XCTAssertTrue(source.contains("showingFileImporter = true"))
    }

    func testDataMenuImportPrefersSidebarThenFallsBackToLibraryNeverAStub() throws {
        let source = try Self.appSource("App/Menus/FocusedCommands/FocusedCommandButtons+SidebarActions.swift")
        XCTAssertTrue(source.contains("@FocusedValue(\\.libraryImportAction) private var libraryImportAction"))
        XCTAssertTrue(source.contains("sidebarActions?.importFiles ?? libraryImportAction"))
        // Disabled state tracks the SAME merged action the buttons call —
        // never independently, which is how a menu item could go
        // enabled-but-no-op.
        XCTAssertTrue(source.contains(".disabled(importAction == nil)"))
    }

    func testHandleFileImportUsesTheStatedModeNotAHardcodedOne() throws {
        // #4452 added Copy/Move via the Data menu; the shared handler must
        // honor whichever mode the presenting surface stated, not always
        // `.link` (which would silently downgrade a user's explicit Copy
        // Files… or Move Files… menu choice to Link).
        let source = try Self.appSource("Views/Library/LibraryView+BottomActionBar.swift")
        XCTAssertTrue(source.contains("let mode = fileImportMode"))
        XCTAssertTrue(source.contains("importFiles(urls, mode: mode, parentId: targetFolderId)"))
    }
}
