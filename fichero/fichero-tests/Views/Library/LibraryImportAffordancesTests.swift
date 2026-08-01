@testable import Fichero
import XCTest

/// Source-surface tests for #4449 — import was unreachable from the Data
/// menu, the contextual menu, and the bottom-bar `+`/Import button. The
/// audit found three genuinely separate implementations:
///   - The sidebar (left tree) had a working picker, but ONLY when the
///     sidebar itself had keyboard focus (`SidebarView.swift`).
///   - The library pane's own bottom-bar Import button flipped
///     `showingFileImporter` with no `.fileImporter` modifier anywhere in
///     the app to answer it — a dead click.
///   - `AddItemMenu`/`ItemTypeRegistry` (a whole unified "+ Add" component
///     with New Folder / Import Link / Copy / Move) was never instantiated
///     outside its own `#Preview` — dead code.
///   - No contextual menu anywhere offered Import at all.
///
/// This fix makes the library pane's bottom bar, folder contextual menu,
/// and empty-area contextual menu share ONE `showingFileImporter` picker
/// and ONE `handleFileImport` handler, each stating an explicit
/// `fileImportTargetFolderId` before presenting — never a bare
/// `parentId: nil` that silently lands documents at the library root.
final class LibraryImportAffordancesTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    // MARK: - Bottom-bar Import button (#4449)

    func testBottomBarImportButtonTargetsCurrentFolderBeforePresenting() throws {
        let source = try Self.appSource("Views/Library/LibraryView+BottomActionBar.swift")
        // The button states its target BEFORE presenting the picker — never
        // a bare `showingFileImporter = true` with an implicit nil target.
        XCTAssertTrue(source.contains("fileImportTargetFolderId = folderId"))
        XCTAssertTrue(source.contains("showingFileImporter = true"))
        // A real `.fileImporter` modifier answers the state flip — the old
        // code set `showingFileImporter` with nothing in the app presenting it.
        XCTAssertTrue(source.contains(".fileImporter("))
        XCTAssertTrue(source.contains("isPresented: $showingFileImporter"))
        XCTAssertTrue(source.contains("onCompletion: handleFileImport"))
    }

    func testHandleFileImportPassesTheStatedTargetFolder() throws {
        let source = try Self.appSource("Views/Library/LibraryView+BottomActionBar.swift")
        XCTAssertTrue(source.contains("func handleFileImport(_ result: Result<[URL], Error>)"))
        // The captured target, not a bare nil — the root-cause bug pattern
        // this issue exists to close.
        XCTAssertTrue(source.contains("let targetFolderId = fileImportTargetFolderId"))
        XCTAssertTrue(source.contains("importFiles(urls, mode: .link, parentId: targetFolderId)"))
    }

    func testCreateNewFolderTargetsCurrentFolderNotRoot() throws {
        let source = try Self.appSource("Views/Library/LibraryView+BottomActionBar.swift")
        // `createCollection(name:)` hardcodes parentId: nil (root) — the
        // same defect class as the import button; `createFolder` takes an
        // explicit parentId.
        XCTAssertTrue(source.contains("createFolder(name: \"New Folder\", parentId: folderId)"))
        XCTAssertFalse(source.contains("createCollection(name: \"New Folder\")"))
    }

    // MARK: - Folder contextual menu (#4449)

    func testFolderContextMenuOffersImportIntoThatFolder() throws {
        let source = try Self.appSource("Views/Library/LibraryView+ContextMenu.swift")
        XCTAssertTrue(source.contains("importIntoFolderMenuItem(for: document)"))
        XCTAssertTrue(source.contains("if document.docType == .folder"))
        // Targets the CLICKED folder's id, not whatever folder happens to be
        // open in the pane — "a `+` on a folder that imports to the root is
        // a different bug wearing the same shape."
        XCTAssertTrue(source.contains("fileImportTargetFolderId = document.id"))
    }

    // MARK: - Empty-area contextual menu (#4449)

    func testEmptyLibraryAreaOffersImport() throws {
        let source = try Self.appSource("Views/Library/ViewModes/LibraryView+IconMode.swift")
        // A contextMenu on the scroll gutter, alongside (not instead of) the
        // per-tile context menus already attached to each document.
        XCTAssertTrue(source.contains("Right-click on empty library area"))
        XCTAssertTrue(source.contains("fileImportTargetFolderId = folderId"))
    }

    // MARK: - One shared presenter, not three implementations

    func testEveryImportSurfaceSharesTheSamePickerState() throws {
        // All three affordances funnel through the SAME `@State` pair
        // declared once on LibraryView — not three separate booleans that
        // would drift the way `AddItemMenu`'s abandoned parallel
        // implementation did.
        let bottomBar = try Self.appSource("Views/Library/LibraryView+BottomActionBar.swift")
        let contextMenu = try Self.appSource("Views/Library/LibraryView+ContextMenu.swift")
        let iconMode = try Self.appSource("Views/Library/ViewModes/LibraryView+IconMode.swift")
        for source in [bottomBar, contextMenu, iconMode] {
            XCTAssertTrue(source.contains("showingFileImporter") || source.contains(".fileImporter("))
        }
        XCTAssertTrue(bottomBar.contains(".fileImporter("))
    }
}
