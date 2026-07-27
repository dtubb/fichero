import Foundation
import XCTest

/// #4124: library grid/list folder cells are REAL drop targets. Before this,
/// cells only had drag sources; the container-level handler imported into the
/// VIEWED folder and every cell highlighted at once.
final class LibraryGridDropTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testFolderCellsAreDropTargetsInIconAndListModes() throws {
        for file in [
            "Views/Library/ViewModes/LibraryView+IconMode.swift",
            "Views/Library/ViewModes/LibraryView+ListView.swift",
            "Views/Library/ViewModes/LibraryView+TableColumns.swift"
        ] {
            let source = try Self.appSource(file)
            XCTAssertTrue(source.contains("LibraryFolderCellDrop("), file)
            XCTAssertTrue(source.contains("moveDraggedItems(items, into:"), file)
        }
    }

    func testDropTargetHighlightsOnlyTheHoveredCell() throws {
        let source = try Self.appSource("Views/Library/ViewModes/LibraryView+CellDrop.swift")
        // Per-cell @State — the whole-pane isTargeted was the all-cells
        // highlight bug.
        XCTAssertTrue(source.contains("@State private var isTargeted"))
        XCTAssertTrue(source.contains("dropDestination(for: LibraryItemDrag.self)"))
        // Moves route through the ONE existing executor, and failures are
        // logged, never silently swallowed.
        XCTAssertTrue(source.contains("documentStore.moveDocument(id, toParent: folder.id)"))
        XCTAssertTrue(source.contains("moves failed"))
    }

    func testSelfDropsAndNonDocumentPayloadsAreRejected() throws {
        let source = try Self.appSource("Views/Library/ViewModes/LibraryView+CellDrop.swift")
        XCTAssertTrue(source.contains(".filter { $0 != folder.id }"))
        XCTAssertTrue(source.contains("case .artifact, .note, .annotation:"))
        XCTAssertTrue(source.contains("guard folder.docType == .folder"))
    }
}

/// #4125: the first pinch on a PDF must not snap back to fit. autoScales is
/// disabled at pinch BEGIN (PinchOwningPDFView.magnify), not on the first
/// scale-change notification — by then PDFKit had already re-fit mid-gesture.
final class PDFFirstPinchTests: XCTestCase {
    func testPinchDisablesAutoScalesAtGestureStart() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Preview/PDFViewer/PDFPageView.swift")
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
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Library/LibraryView+ContextMenu.swift")
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
}

/// Default Workflows rows read as locked (Daniel, 2026-07-27): a trailing
/// lock badge on the container, its preset subfolders, and mirrored rows.
final class SidebarLockedRowBadgeTests: XCTestCase {
    func testLockedRowsShowTrailingLockBadge() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Sidebar/ItemRow/SidebarItemRow+Label.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(source.contains("doc.isDefaultWorkflowFolder || doc.isWorkflowNode"))
        XCTAssertTrue(source.contains("Image(systemName: \"lock.fill\")"))
        XCTAssertTrue(source.contains("accessibilityLabel(\"Read-only\")"))
    }
}
