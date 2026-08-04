@testable import Fichero
import XCTest

/// Truth-table coverage for the compact (iPhone) reader-push resolution (#2666):
/// `ContentView.resolveCompactReaderLeaf` decides WHAT the tap pushes, and
/// `LibraryView.plainTapNavigatesInto` decides whether a plain tap drills into
/// a container. Both are `nonisolated static` pure helpers — no live view.
final class CompactReaderLeafTests: XCTestCase {

    private func doc(_ id: String, folder: Bool = false) -> Document {
        Document(id: id, docType: folder ? .folder : .file, name: id)
    }

    // MARK: - resolveCompactReaderLeaf

    /// A promoted detailDocument wins over any id lookup.
    func testDetailDocumentWinsOverSelection() {
        let detail = doc("detail")
        let other = doc("other")
        let leaf = ContentView.resolveCompactReaderLeaf(
            detailDocument: detail,
            selectedId: "other",
            displayedDocuments: [other],
            fallbackDocuments: [other]
        )
        XCTAssertEqual(leaf?.id, "detail")
    }

    /// No detailDocument: the selected id resolves from the DISPLAYED list.
    func testSelectionResolvesFromDisplayedDocuments() {
        let shown = doc("hit")
        let leaf = ContentView.resolveCompactReaderLeaf(
            detailDocument: nil,
            selectedId: "hit",
            displayedDocuments: [shown],
            fallbackDocuments: []
        )
        XCTAssertEqual(leaf?.id, "hit")
    }

    /// Displayed and current momentarily disagree (#2666): the fallback list
    /// still resolves the tap.
    func testSelectionFallsBackToCurrentDocuments() {
        let current = doc("late")
        let leaf = ContentView.resolveCompactReaderLeaf(
            detailDocument: nil,
            selectedId: "late",
            displayedDocuments: [],
            fallbackDocuments: [current]
        )
        XCTAssertEqual(leaf?.id, "late")
    }

    /// The displayed list wins when both contain the id — it is what the user
    /// actually tapped (transient search shows out-of-folder hits).
    func testDisplayedDocumentsWinOverFallback() {
        var displayed = doc("d1")
        displayed.name = "displayed-copy"
        var fallback = doc("d1")
        fallback.name = "fallback-copy"
        let leaf = ContentView.resolveCompactReaderLeaf(
            detailDocument: nil,
            selectedId: "d1",
            displayedDocuments: [displayed],
            fallbackDocuments: [fallback]
        )
        XCTAssertEqual(leaf?.name, "displayed-copy")
    }

    /// Folders NEVER push the reader — a folder tap drills in place instead.
    func testFolderNeverResolvesAsLeaf() {
        let folder = doc("f", folder: true)
        XCTAssertNil(ContentView.resolveCompactReaderLeaf(
            detailDocument: folder,
            selectedId: nil,
            displayedDocuments: [],
            fallbackDocuments: []
        ))
        XCTAssertNil(ContentView.resolveCompactReaderLeaf(
            detailDocument: nil,
            selectedId: "f",
            displayedDocuments: [folder],
            fallbackDocuments: [folder]
        ))
    }

    /// Nothing selected, nothing promoted: no push.
    func testEmptySelectionResolvesNil() {
        XCTAssertNil(ContentView.resolveCompactReaderLeaf(
            detailDocument: nil,
            selectedId: nil,
            displayedDocuments: [doc("a")],
            fallbackDocuments: [doc("b")]
        ))
    }

    /// A selected id absent from BOTH lists (stale restored selection) must
    /// not push anything.
    func testUnresolvableSelectionResolvesNil() {
        XCTAssertNil(ContentView.resolveCompactReaderLeaf(
            detailDocument: nil,
            selectedId: "gone",
            displayedDocuments: [doc("a")],
            fallbackDocuments: [doc("b")]
        ))
    }

    // MARK: - plainTapNavigatesInto (#2666 folder drill-in)

    /// Compact width (iPhone): a plain tap on a container ALWAYS drills in —
    /// there is no persistent sidebar to navigate folders with, even though the
    /// shell's `showSidebar` state stays true.
    func testCompactPlainTapDrillsIntoContainerRegardlessOfSidebarState() {
        for sidebarHidden in [true, false] {
            XCTAssertTrue(
                LibraryView.plainTapNavigatesInto(
                    isNavigableContainer: true,
                    sidebarHidden: sidebarHidden,
                    isCompactWidth: true
                ),
                "sidebarHidden=\(sidebarHidden)"
            )
        }
    }

    /// Regular width: unchanged behavior — drill in only when the sidebar is
    /// hidden; with a visible sidebar a single click is selection.
    func testRegularPlainTapDrillsOnlyWhenSidebarHidden() {
        XCTAssertTrue(LibraryView.plainTapNavigatesInto(
            isNavigableContainer: true,
            sidebarHidden: true,
            isCompactWidth: false
        ))
        XCTAssertFalse(LibraryView.plainTapNavigatesInto(
            isNavigableContainer: true,
            sidebarHidden: false,
            isCompactWidth: false
        ))
    }

    /// Non-containers never navigate-in, on any width or sidebar state.
    func testNonContainerNeverNavigatesInto() {
        for sidebarHidden in [true, false] {
            for compact in [true, false] {
                XCTAssertFalse(
                    LibraryView.plainTapNavigatesInto(
                        isNavigableContainer: false,
                        sidebarHidden: sidebarHidden,
                        isCompactWidth: compact
                    ),
                    "sidebarHidden=\(sidebarHidden) compact=\(compact)"
                )
            }
        }
    }
}
