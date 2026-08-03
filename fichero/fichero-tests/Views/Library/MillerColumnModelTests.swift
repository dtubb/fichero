@testable import Fichero
import Foundation
import XCTest

/// #4160 step 4 — pure path logic for the Miller column browser. The path is
/// a chain of folder IDS (never Document snapshots): every render resolves
/// segments live, and a segment that stops resolving (deleted, moved away,
/// no longer a folder) truncates the path at that depth.
final class MillerColumnModelTests: XCTestCase {
    func testLivePathKeepsFullyResolvablePath() {
        let live = ["a", "b", "c"]
        XCTAssertEqual(MillerColumnModel.livePath(["a", "b", "c"]) { live.contains($0) },
                       ["a", "b", "c"])
    }

    func testLivePathTruncatesAtTheFirstDeadSegment() {
        // "b" was deleted mid-session: everything above it is still valid,
        // everything below no longer exists — truncate AT that depth, even
        // though "c" itself still resolves.
        let live = ["a", "c"]
        XCTAssertEqual(MillerColumnModel.livePath(["a", "b", "c"]) { live.contains($0) },
                       ["a"])
    }

    func testLivePathOnEmptyAndFullyDeadPaths() {
        XCTAssertEqual(MillerColumnModel.livePath([]) { _ in true }, [])
        XCTAssertEqual(MillerColumnModel.livePath(["a", "b"]) { _ in false }, [])
    }

    func testDescendKeepsAncestorsAndReplacesTheDeeperTail() {
        // Selecting folder "x" in column 1 (children of "a") closes the old
        // "b"/"c" tail and discloses "x".
        XCTAssertEqual(MillerColumnModel.descend(path: ["a", "b", "c"], atDepth: 1, into: "x"),
                       ["a", "x"])
        // Column 0 selection replaces the whole path.
        XCTAssertEqual(MillerColumnModel.descend(path: ["a", "b"], atDepth: 0, into: "x"),
                       ["x"])
        // Deepest column extends the path.
        XCTAssertEqual(MillerColumnModel.descend(path: ["a"], atDepth: 1, into: "x"),
                       ["a", "x"])
    }

    func testTruncateClosesColumnsBelowANonFolderSelection() {
        XCTAssertEqual(MillerColumnModel.truncate(path: ["a", "b", "c"], forSelectionAtDepth: 1),
                       ["a"])
        XCTAssertEqual(MillerColumnModel.truncate(path: ["a"], forSelectionAtDepth: 0), [])
    }

    func testClampActiveDepthStaysWithinExistingColumns() {
        // path.count segments → path.count + 1 columns (root + one each).
        XCTAssertEqual(MillerColumnModel.clampActiveDepth(5, pathCount: 2), 2)
        XCTAssertEqual(MillerColumnModel.clampActiveDepth(-1, pathCount: 2), 0)
        XCTAssertEqual(MillerColumnModel.clampActiveDepth(1, pathCount: 2), 1)
        // A truncated path pulls a deep active column back into range.
        XCTAssertEqual(MillerColumnModel.clampActiveDepth(3, pathCount: 0), 0)
    }

    // MARK: - Parity bar (source guard, mirrors LibraryListKeyboardTests)

    func testColumnsModeMeetsTheSharedInteractionBar() throws {
        let base = try AppSource.root().appendingPathComponent("Views/Library")
        let columns = try String(
            contentsOf: base.appendingPathComponent("ViewModes/Columns/LibraryView+ColumnsView.swift"),
            encoding: .utf8
        )
        // Reuses the EXISTING stores + selection model, no parallel state.
        XCTAssertTrue(columns.contains("documentStore.children(of: folderId)"))
        XCTAssertTrue(columns.contains("LibrarySelectableRow("))
        XCTAssertTrue(columns.contains("handleTap(doc)"))
        // Parity bar from steps 1-3: rename, a11y, hover, diffing, deselect.
        XCTAssertTrue(columns.contains("EditableDocumentName("))
        XCTAssertTrue(columns.contains("accessibilityIdentifier(\"libraryColumnRow."))
        XCTAssertTrue(columns.contains("LibraryRowHoverWash"))
        XCTAssertTrue(columns.contains(".equatable()"))
        XCTAssertTrue(columns.contains("selection.removeAll()"))
        XCTAssertTrue(columns.contains("documentContextMenu(for: doc)"))
        // Keyboard: the shared handler navigates the ACTIVE column, and
        // Return/Space/delete resolve deep-column ids through one seam.
        let nav = try String(
            contentsOf: base.appendingPathComponent("LibraryView+ArrowNavigation.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(nav.contains("var keyboardNavigationDocuments: [Document]"))
        XCTAssertTrue(nav.contains("func navigableDocument(for id: String) -> Document?"))
        XCTAssertTrue(nav.contains("handleColumnsArrowKey(direction: direction)"))
    }

    func testPreviewColumnReusesThePreviewSurfaceForSingleNonFolderSelection() throws {
        let base = try AppSource.root().appendingPathComponent("Views/Library")
        let columns = try String(
            contentsOf: base.appendingPathComponent("ViewModes/Columns/LibraryView+ColumnsView.swift"),
            encoding: .utf8
        )
        // The trailing preview column is the EXISTING Preview surface
        // (EditorView = source viewer) — never a Reader/Inspector variant —
        // and only for a SINGLE non-folder selection (Finder behavior).
        XCTAssertTrue(columns.contains("EditorView(document: previewDoc)"))
        XCTAssertTrue(columns.contains("selection.count == 1"))
        XCTAssertTrue(columns.contains("doc.docType != .folder"))
        XCTAssertFalse(columns.contains("InspectorView("))
        XCTAssertFalse(columns.contains("ReaderView("))
    }
}
