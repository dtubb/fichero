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
        let url = try AppSource.root()
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
        // `mode:` is deliberately NOT pinned here. This assertion read
        // `mode: .link` until #4452 made the handler honour the presenting
        // surface's mode, and went on asserting a string the source had
        // stopped containing — a stale guard is indistinguishable from a
        // broken feature, and this one guards the TARGET FOLDER, which is what
        // its name says. The mode is pinned by
        // LibraryImportFocusedValueTests.testHandleFileImportUsesTheStatedMode…
        XCTAssertTrue(source.contains("importFiles(urls, mode: mode, parentId: targetFolderId)"))
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

    /// There is ONE empty-area menu, defined once. The icon gutter and the
    /// empty state both mount it; neither carries its own copy of the
    /// three-line "state the target, then present" sequence, which is how the
    /// bottom bar and `AddItemMenu` drifted apart to begin with.
    func testEmptyAreaImportMenuIsDefinedOnceAndSharedByBothSurfaces() throws {
        let contextMenu = try Self.appSource("Views/Library/LibraryView+ContextMenu.swift")
        XCTAssertTrue(contextMenu.contains("var libraryEmptyAreaImportMenu: some View"))
        XCTAssertTrue(contextMenu.contains("fileImportTargetFolderId = folderId"))
        XCTAssertTrue(contextMenu.contains("showingFileImporter = true"))

        // Both mounting surfaces call the shared builder, not their own copy.
        let iconMode = try Self.appSource("Views/Library/ViewModes/Icon/LibraryView+IconMode.swift")
        XCTAssertTrue(iconMode.contains(".contextMenu { libraryEmptyAreaImportMenu }"))
        XCTAssertFalse(iconMode.contains("Label(\"Import Files…\""))

        let emptyState = try Self.appSource("Views/Library/LibraryView+FilterAndBatch.swift")
        XCTAssertTrue(emptyState.contains("libraryEmptyAreaImportMenu"))
        XCTAssertFalse(emptyState.contains("Label(\"Import Files…\""))
    }

    /// The case the first #4449 fix missed, and the one a NEW USER hits:
    /// an empty library never renders the icon grid, so the gutter menu was
    /// unreachable exactly when the library had nothing in it.
    /// `libraryRowsOrEmptyState` branches to `emptyState` BEFORE the
    /// `displayMode` switch — assert that ordering, because it is what makes
    /// the gutter menu insufficient on its own.
    func testEmptyLibraryShowsEmptyStateBeforeAnyViewMode() throws {
        let library = try Self.appSource("Views/Library/LibraryView.swift")
        XCTAssertTrue(library.contains("if isCollectionEmpty {"))
        XCTAssertTrue(library.contains("emptyState"))
        guard let emptyBranch = library.range(of: "if isCollectionEmpty {"),
              let modeSwitch = library.range(of: "switch displayMode {") else {
            return XCTFail("libraryRowsOrEmptyState no longer has both branches")
        }
        XCTAssertLessThan(
            emptyBranch.lowerBound, modeSwitch.lowerBound,
            "The empty branch must precede the view-mode switch; if a mode can render "
                + "an empty library, the gutter menu is no longer the missing case."
        )
    }

    /// The empty state's menu is gated on the reason, not shown blindly —
    /// a filtered-out body would otherwise offer to import into a container
    /// the user cannot see. The gate's behavior is covered by
    /// `LibraryEmptyReasonTests.importOfferedByExactlyOneReason`.
    func testEmptyStateImportIsGatedOnTheReason() throws {
        let source = try Self.appSource("Views/Library/LibraryView+FilterAndBatch.swift")
        XCTAssertTrue(source.contains("if reason.offersImport {"))
    }

    // MARK: - One shared presenter, not four implementations

    /// The whole point of the issue: four affordances, ONE action. Each
    /// surface must reach `showingFileImporter` + `handleFileImport`, and
    /// there must be exactly one `.fileImporter` presenter answering them.
    func testAllFourAffordancesReachTheOneImportAction() throws {
        let bottomBar = try Self.appSource("Views/Library/LibraryView+BottomActionBar.swift")
        let contextMenu = try Self.appSource("Views/Library/LibraryView+ContextMenu.swift")
        let iconMode = try Self.appSource("Views/Library/ViewModes/Icon/LibraryView+IconMode.swift")
        let emptyState = try Self.appSource("Views/Library/LibraryView+FilterAndBatch.swift")
        let libraryView = try Self.appSource("Views/Library/LibraryView.swift")

        // (a) Data menu → Import, via the narrow focused value (#4452).
        XCTAssertTrue(libraryView.contains(".focusedValue(\\.libraryImportAction)"))
        XCTAssertTrue(libraryView.contains("showingFileImporter = true"))
        // (b) folder contextual menu, (c) empty-area menu, (d) bottom bar.
        XCTAssertTrue(contextMenu.contains("importIntoFolderMenuItem(for: document)"))
        XCTAssertTrue(contextMenu.contains("var libraryEmptyAreaImportMenu: some View"))
        XCTAssertTrue(iconMode.contains("libraryEmptyAreaImportMenu"))
        XCTAssertTrue(emptyState.contains("libraryEmptyAreaImportMenu"))
        XCTAssertTrue(bottomBar.contains("fileImportTargetFolderId = folderId"))

        // ONE presenter, in one place, answering all of them.
        let presenters = [bottomBar, contextMenu, iconMode, emptyState, libraryView]
            .filter { $0.contains(".fileImporter(") }
        XCTAssertEqual(
            presenters.count, 1,
            "Exactly one `.fileImporter` may answer `showingFileImporter`; a second "
                + "presenter is the start of the divergence #4449 exists to close."
        )
        XCTAssertTrue(bottomBar.contains(".fileImporter("))
        XCTAssertTrue(bottomBar.contains("onCompletion: handleFileImport"))
    }

    /// No affordance may present the picker without first stating its target
    /// — a bare `showingFileImporter = true` silently lands files at the
    /// library root. Counted per file: every flip is preceded by a
    /// `fileImportTargetFolderId` assignment.
    func testNoAffordancePresentsThePickerWithoutStatingATarget() throws {
        for path in [
            "Views/Library/LibraryView+BottomActionBar.swift",
            "Views/Library/LibraryView+ContextMenu.swift",
            "Views/Library/LibraryView.swift"
        ] {
            // Comment lines dropped first: these files DOCUMENT the
            // state-then-present sequence in prose, and counting those
            // mentions would make the guard fail on correct code — a false
            // alarm is how a guard gets deleted instead of fixed.
            let source = try Self.appSource(path)
                .split(separator: "\n", omittingEmptySubsequences: false)
                .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
                .joined(separator: "\n")
            let flips = source.components(separatedBy: "showingFileImporter = true").count - 1
            let targets = source.components(separatedBy: "fileImportTargetFolderId = ").count - 1
            XCTAssertGreaterThan(flips, 0, "\(path): no import affordance left at all.")
            XCTAssertEqual(
                flips, targets,
                "\(path): \(flips) picker presentation(s) but \(targets) stated target(s) — "
                    + "an unstated target imports to the library root."
            )
        }
    }
}
