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
            ("Views/Library/ViewModes/LibraryView+ListView.swift", ".draggable(libraryItemDrag(for: doc))"),
            ("Views/Library/ViewModes/LibraryView+IconMode.swift", ".draggable(libraryItemDrag(for: doc))"),
            ("Views/Inspector/Artifacts/ArtifactListView.swift", ".draggable(LibraryItemDrag("),
            ("Views/Inspector/Notes/Annotations/AnnotationListView.swift", ".draggable(LibraryItemDrag("),
            ("Views/Library/Notes/NoteListView.swift", ".draggable(LibraryItemDrag("),
            ("Views/Library/ViewModes/LibraryView+TableColumns.swift", ".draggable(libraryItemDrag(for: page))")
        ]

        for (path, marker) in surfaces {
            let source = try String(contentsOf: root.appendingPathComponent(path), encoding: .utf8)
            XCTAssertTrue(source.contains(marker), path)
        }
    }
}
