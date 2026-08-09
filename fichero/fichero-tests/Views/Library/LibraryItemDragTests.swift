@testable import Fichero
import XCTest

final class LibraryItemDragTests: XCTestCase {

    func testLibraryItemDragExportsReadableText() {
        let item = LibraryItemDrag(kind: .annotation, id: "annotation-1", documentId: "page-1", text: "Important")

        XCTAssertEqual(item.exportText, "Annotation: Important")
    }

    func testExternalFileDragsSuggestTheDocumentName() throws {
        let root = try AppSource.root()
        // SidebarDragID's Transferable moved out of SidebarItemRow.swift in
        // the 2026-08-09 row slimming; the export contract is what's pinned.
        for path in ["Models/Document.swift", "Views/Sidebar/ItemRow/SidebarDragID.swift"] {
            let source = try String(contentsOf: root.appendingPathComponent(path), encoding: .utf8)
            XCTAssertTrue(source.contains(".suggestedFileName(\\.name)"), path)
        }
    }

    func testLibrarySurfacesUseCommonDragPayload() throws {
        let root = try AppSource.root()
        // LibraryView+DisplayModes.swift / LibraryView+TableMapViews.swift were
        // renamed/split; the doc-drag marker now lives in both IconMode and
        // ListView, and the page-drag marker in TableColumns.
        let surfaces = [
            ("Views/Library/ViewModes/Icon/LibraryView+IconMode.swift", ".draggable(libraryItemDrag(for: doc))"),
            ("Views/Library/ViewModes/List/LibraryView+ListView.swift", ".draggable(libraryItemDrag(for: doc))"),
            ("Views/Inspector/Artifacts/ArtifactListView.swift", ".draggable(LibraryItemDrag("),
            ("Views/Inspector/Notes/Annotations/AnnotationListView.swift", ".draggable(LibraryItemDrag("),
            ("Views/Library/Notes/NoteListView.swift", ".draggable(LibraryItemDrag("),
            ("Views/Library/ViewModes/Table/LibraryView+TableColumns.swift", ".draggable(libraryItemDrag(for: page))")
        ]

        for (path, marker) in surfaces {
            let source = try String(contentsOf: root.appendingPathComponent(path), encoding: .utf8)
            XCTAssertTrue(source.contains(marker), path)
        }
    }
}
