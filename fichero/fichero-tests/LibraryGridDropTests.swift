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
            "Views/Library/ViewModes/LibraryView+ListView.swift"
        ] {
            let source = try Self.appSource(file)
            XCTAssertTrue(source.contains("LibraryFolderCellDrop("), file)
            XCTAssertTrue(source.contains("moveDraggedItems(items, into: doc)"), file)
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
