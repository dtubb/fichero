@testable import Fichero
import XCTest

final class LibraryItemDragTests: XCTestCase {

    func testLibraryItemDragExportsReadableText() {
        let item = LibraryItemDrag(kind: .annotation, id: "annotation-1", documentId: "page-1", text: "Important")

        XCTAssertEqual(item.exportText, "Annotation: Important")
    }

    func testLibrarySurfacesUseCommonDragPayload() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
        let surfaces = [
            ("Views/Library/LibraryView+DisplayModes.swift", ".draggable(libraryItemDrag(for: doc))"),
            ("Views/Library/Inspector/ArtifactListView.swift", ".draggable(LibraryItemDrag("),
            ("Views/Library/Inspector/AnnotationListView.swift", ".draggable(LibraryItemDrag("),
            ("Views/Notes/NoteListView.swift", ".draggable(LibraryItemDrag("),
            ("Views/Library/LibraryView+TableMapViews.swift", ".draggable(libraryItemDrag(for: page))")
        ]

        for (path, marker) in surfaces {
            let source = try String(contentsOf: root.appendingPathComponent(path), encoding: .utf8)
            XCTAssertTrue(source.contains(marker), path)
        }
    }
}
