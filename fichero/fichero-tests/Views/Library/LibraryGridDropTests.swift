import Foundation
import XCTest

/// #4124: library grid/list folder cells are REAL drop targets. Before this,
/// cells only had drag sources; the container-level handler imported into the
/// VIEWED folder and every cell highlighted at once.
final class LibraryGridDropTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    // #4474/#4475 UPDATED these three. What #4124 established — folder cells
    // are real drop targets, only the hovered one highlights, self-drops and
    // non-document payloads are refused — is all still true and still pinned.
    // What changed is HOW, and the old assertions pinned the how:
    //
    //   - `.dropDestination(for: LibraryItemDrag.self)` was the #4474 bug. A
    //     destination typed on the library's payload matches a sidebar drag not
    //     at all, so dragging a sidebar row onto a folder cell did nothing.
    //   - `moveDraggedItems` always moved, which is the #4475 B bug.
    //   - the non-document exclusion moved into the shared classifier, so it is
    //     now made once for every surface instead of once per destination.
    //
    // The behavioural replacements live in `LibraryDropPairingTests`.

    func testFolderCellsAreDropTargetsInEveryViewMode() throws {
        for file in [
            "Views/Library/ViewModes/LibraryView+IconMode.swift",
            "Views/Library/ViewModes/LibraryView+ListView.swift",
            "Views/Library/ViewModes/LibraryView+TableColumns.swift",
            "Views/Library/ViewModes/Columns/LibraryView+ColumnsView.swift"
        ] {
            let source = try Self.appSource(file)
            XCTAssertTrue(source.contains("LibraryFolderCellDrop("), file)
            XCTAssertTrue(source.contains("handleFolderCellDrop(providers"), file)
        }
    }

    func testDropTargetHighlightsOnlyTheHoveredCell() throws {
        let source = try Self.appSource("Views/Library/ViewModes/LibraryView+CellDrop.swift")
        // Per-cell @State — the whole-pane isTargeted was the all-cells
        // highlight bug. Unchanged by #4474.
        XCTAssertTrue(source.contains("@State private var isTargeted"))
        // Untyped now, so BOTH in-app drag shapes reach it.
        XCTAssertTrue(source.contains(".onDrop(of: SidebarItemRow.dropTypes"))
        // Moves route through the ONE shared executor, and failures are now
        // REPORTED, not merely logged.
        XCTAssertTrue(source.contains("applyLibraryItemDropOperation("))
        XCTAssertTrue(source.contains("windowState.dropErrorMessage ="))
    }

    func testSelfDropsAndNonFolderTargetsAreRejected() throws {
        let source = try Self.appSource("Views/Library/ViewModes/LibraryView+CellDrop.swift")
        XCTAssertTrue(source.contains("$0 != folder.id"))
        XCTAssertTrue(source.contains("guard folder.docType == .folder"))
        // The artifact/note/annotation exclusion now lives in the shared
        // classifier — one exclusion for every surface, not one per destination.
        let classifier = try Self.appSource("Views/Sidebar/ItemRow/SidebarDropClassification.swift")
        XCTAssertTrue(classifier.contains("case .artifact, .note, .annotation:"))
    }
}

/// #4125: the first pinch on a PDF must not snap back to fit. autoScales is
/// disabled at pinch BEGIN (PinchOwningPDFView.magnify), not on the first
/// scale-change notification — by then PDFKit had already re-fit mid-gesture.
final class PDFFirstPinchTests: XCTestCase {
    func testPinchDisablesAutoScalesAtGestureStart() throws {
        let url = try AppSource.root().appendingPathComponent("Views/Preview/PDFViewer/PDFPageView.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(source.contains("class PinchOwningPDFView: PDFView"))
        XCTAssertTrue(source.contains("override func magnify(with event: NSEvent)"))
        XCTAssertTrue(source.contains("let view = PinchOwningPDFView()"))
    }
}

/// #4121 parity: the same document offers the same actions in the grid menu
/// as in the sidebar row menu.
final class LibraryContextMenuParityTests: XCTestCase {
    func testGridMenuGainsSidebarParityActions() throws {
        let url = try AppSource.root().appendingPathComponent("Views/Library/LibraryView+ContextMenu.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(source.contains("Label(\"Add to Chat\""))
        XCTAssertTrue(source.contains("Label(\"Duplicate\""))
        XCTAssertTrue(source.contains("Label(\"Make Alias\""))
        XCTAssertTrue(source.contains("Label(\"Delete\""))
        // Same audited action + alias semantics as the sidebar row.
        XCTAssertTrue(source.contains("name: \"document.duplicate\""))
        XCTAssertTrue(source.contains("document.isAlias ? (document.aliasTargetId ?? document.id) : document.id"))
        // Delete honors the multi-selection when the clicked row is in it.
        XCTAssertTrue(source.contains("selection.contains(document.id)"))
    }

    /// Reverse parity (#4121): the grid's Bookmark…/Add to Workspace… picker
    /// actions on the sidebar row, presented per-row so the clicked row's OWN
    /// library services back the sheet (sidebar rows span libraries).
    func testSidebarRowGainsGridPickerActions() throws {
        let url = try AppSource.root()
            .appendingPathComponent("Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(source.contains("Label(\"Bookmark…\""))
        XCTAssertTrue(source.contains("Label(\"Add to Workspace…\""))
        XCTAssertTrue(source.contains("Label(\"Export…\""))

        let bodyURL = try AppSource.root()
            .appendingPathComponent("Views/Sidebar/ItemRow/SidebarItemRow+Presentation+Body.swift")
        let body = try String(contentsOf: bodyURL, encoding: .utf8)
        XCTAssertTrue(body.contains(".sheet(item: $workspacePickerDocument)"))
        XCTAssertTrue(body.contains(".sheet(item: $bookmarkPickerDocument)"))
        // The sheet must inject the ROW's library services, not inherit
        // whatever library happens to be active in the window.
        XCTAssertTrue(body.contains(".environment(library.bookmarkService)"))
    }

    /// Export… (#4121) exists on BOTH surfaces and both funnel through
    /// DocumentExporter → SidebarItemRow.exportSourceFile — the storage-service
    /// path drag-out uses. One implementation, no divergent naming/auth.
    func testExportSharesTheDragOutPath() throws {
        let root = try AppSource.root()
        let grid = try String(
            contentsOf: root.appendingPathComponent("Views/Library/LibraryView+ContextMenu.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(grid.contains("DocumentExporter.exportViaSavePanel"))
        XCTAssertTrue(grid.contains("Label(\"Export…\""))
        let exporter = try String(
            contentsOf: root.appendingPathComponent("Views/Library/Export/DocumentExporter.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(exporter.contains("SidebarDragID.exportSourceFile"))
    }

    /// The Run Workflow submenu body is ONE shared implementation (#4121):
    /// both context menus render RunWorkflowSubmenuItems, and neither keeps
    /// a private copy of the grouping logic.
    func testRunWorkflowSubmenuIsShared() throws {
        let root = try AppSource.root()
        let sidebar = try String(
            contentsOf: root.appendingPathComponent("Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift"),
            encoding: .utf8
        )
        let grid = try String(
            contentsOf: root.appendingPathComponent("Views/Library/LibraryView+ContextMenu.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(sidebar.contains("RunWorkflowSubmenuItems(workflows:"))
        XCTAssertTrue(grid.contains("RunWorkflowSubmenuItems(workflows:"))
        XCTAssertFalse(sidebar.contains("func workflowMenuItems("))
        XCTAssertFalse(grid.contains("func workflowSubmenuItems("))
    }
}

/// Default Workflows rows read as locked (the user, 2026-07-27): a trailing
/// lock badge on the container, its preset subfolders, and mirrored rows.
final class SidebarLockedRowBadgeTests: XCTestCase {
    func testLockedRowsShowTrailingLockBadge() throws {
        let url = try AppSource.root()
            .appendingPathComponent("Views/Sidebar/ItemRow/SidebarItemRow+Label.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        // Reads the ITEM's ancestry answer, not the document's id shape: a
        // re-homed legacy folder keeps its old id and would badge nothing
        // (#4200). Behaviour is unchanged for seeded rows.
        XCTAssertTrue(source.contains("item.isDefaultWorkflowFolder || doc.isWorkflowNode"))
        XCTAssertTrue(source.contains("Image(systemName: \"lock.fill\")"))
        XCTAssertTrue(source.contains("accessibilityLabel(\"Read-only\")"))
    }
}
