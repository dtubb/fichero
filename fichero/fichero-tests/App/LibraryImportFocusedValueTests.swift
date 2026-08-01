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
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testLibraryImportActionKeyIsNarrowNotSidebarActions() throws {
        let source = try Self.appSource("App/Menus/FocusedCommandButtons+FocusedValues.swift")
        XCTAssertTrue(source.contains("struct LibraryImportActionKey: FocusedValueKey"))
        XCTAssertTrue(source.contains("typealias Value = (IngestMode) -> Void"))
        XCTAssertTrue(source.contains("var libraryImportAction: LibraryImportActionKey.Value?"))
    }

    func testLibraryViewPublishesItsOwnImportActionWhenFocused() throws {
        let source = try Self.appSource("Views/Library/LibraryView.swift")
        XCTAssertTrue(source.contains(".focusedValue(\\.libraryImportAction)"))
        // States mode + target before presenting — same discipline as the
        // other three surfaces (#4449).
        XCTAssertTrue(source.contains("fileImportMode = mode"))
        XCTAssertTrue(source.contains("fileImportTargetFolderId = folderId"))
        XCTAssertTrue(source.contains("showingFileImporter = true"))
    }

    func testDataMenuImportPrefersSidebarThenFallsBackToLibraryNeverAStub() throws {
        let source = try Self.appSource("App/Menus/FocusedCommandButtons+SidebarActions.swift")
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
