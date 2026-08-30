import CoreGraphics
@testable import Fichero
import XCTest

/// Regions as first-class objects (2026-08-29): the shared selection holder,
/// the pure hit-testing/move math behind click-to-select and drag-to-move,
/// and the ephemeral marquee seam the workflow bar will read.
@MainActor
final class RegionSelectionTests: XCTestCase {

    // MARK: - RegionSelection semantics

    func testSelectReplacesToggleAccumulates() {
        let selection = RegionSelection()
        selection.select(3, artifactId: "a", documentId: "d")
        XCTAssertEqual(selection.indices, [3])

        selection.toggle(5, artifactId: "a", documentId: "d")
        XCTAssertEqual(selection.indices, [3, 5])

        // Toggling an already-selected index removes it (row click-off).
        selection.toggle(3, artifactId: "a", documentId: "d")
        XCTAssertEqual(selection.indices, [5])

        // Plain click replaces, never appends.
        selection.select(1, artifactId: "a", documentId: "d")
        XCTAssertEqual(selection.indices, [1])
    }

    func testSelectionNeverSpansArtifacts() {
        let selection = RegionSelection()
        selection.toggle(0, artifactId: "a", documentId: "d")
        selection.toggle(1, artifactId: "a", documentId: "d")
        // Selecting in another artifact abandons the old selection — two
        // geometries' indices share no meaning.
        selection.toggle(7, artifactId: "b", documentId: "d")
        XCTAssertEqual(selection.artifactId, "b")
        XCTAssertEqual(selection.indices, [7])
        XCTAssertFalse(selection.isSelected(0, in: "a"))
    }

    func testInvalidateClearsOnlyItsArtifact() {
        let selection = RegionSelection()
        selection.select(2, artifactId: "a", documentId: "d")
        selection.invalidate(artifactId: "other")
        XCTAssertEqual(selection.indices, [2], "an edit to another artifact must not clear this selection")
        selection.invalidate(artifactId: "a")
        XCTAssertTrue(selection.isEmpty)
        XCTAssertNil(selection.artifactId)
    }

    // MARK: - Hit testing

    private let size = CGSize(width: 200, height: 100)
    private let unit = CGRect(x: 0, y: 0, width: 1, height: 1)

    func testPickFindsContainingBox() {
        let boxes: [[Double]] = [
            [0.0, 0.0, 0.5, 0.5],
            [0.5, 0.5, 0.5, 0.5]
        ]
        // Center of the second box: (0.75, 0.75) → view (150, 75).
        let hit = RegionHitTesting.pick(
            at: CGPoint(x: 150, y: 75), boxes: boxes, in: size, visible: unit
        )
        XCTAssertEqual(hit, 1)
    }

    func testPickPrefersSmallestBoxWhenNested() {
        let boxes: [[Double]] = [
            [0.0, 0.0, 1.0, 1.0],           // page-sized
            [0.4, 0.4, 0.2, 0.2]            // little region inside it
        ]
        let hit = RegionHitTesting.pick(
            at: CGPoint(x: 100, y: 50), boxes: boxes, in: size, visible: unit
        )
        XCTAssertEqual(hit, 1, "the small box must stay clickable inside the big one")
    }

    func testPickMissReturnsNil() {
        let boxes: [[Double]] = [[0.0, 0.0, 0.1, 0.1]]
        let hit = RegionHitTesting.pick(
            at: CGPoint(x: 190, y: 90), boxes: boxes, in: size, visible: unit
        )
        XCTAssertNil(hit)
    }

    // MARK: - Move math

    func testMovedTranslatesThroughVisibleWindow() {
        // Zoomed to the left half: a 100pt drag across a 200pt view is half
        // the VISIBLE window = 0.25 of the image.
        let visible = CGRect(x: 0, y: 0, width: 0.5, height: 0.5)
        let moved = RegionHitTesting.moved(
            bbox: [0.1, 0.1, 0.2, 0.1],
            byViewDelta: CGSize(width: 100, height: 0),
            in: size, visible: visible
        )
        XCTAssertEqual(moved?[0] ?? -1, 0.35, accuracy: 0.0001)
        XCTAssertEqual(moved?[1] ?? -1, 0.1, accuracy: 0.0001)
        XCTAssertEqual(moved?[2] ?? -1, 0.2, accuracy: 0.0001)
    }

    func testMovedClampsToPageBounds() {
        let moved = RegionHitTesting.moved(
            bbox: [0.7, 0.8, 0.2, 0.1],
            byViewDelta: CGSize(width: 500, height: 500),
            in: size, visible: CGRect(x: 0, y: 0, width: 1, height: 1)
        )
        // x clamps to 1 - width, y to 1 - height: the region stays on-page.
        XCTAssertEqual(moved?[0] ?? -1, 0.8, accuracy: 0.0001)
        XCTAssertEqual(moved?[1] ?? -1, 0.9, accuracy: 0.0001)
    }

    // MARK: - Marquee seam

    func testMarqueeAddOnNewDocumentResetsSet() {
        let marquees = PreviewMarqueeSelection()
        marquees.add([0.1, 0.1, 0.2, 0.2], documentId: "doc1")
        marquees.add([0.5, 0.5, 0.2, 0.2], documentId: "doc1")
        XCTAssertEqual(marquees.count, 2)
        marquees.add([0.0, 0.0, 0.1, 0.1], documentId: "doc2")
        XCTAssertEqual(marquees.documentId, "doc2")
        XCTAssertEqual(marquees.count, 1, "marquees never outlive their page")
    }

    func testMarqueeRemoveSelected() {
        let marquees = PreviewMarqueeSelection()
        marquees.add([0.1, 0.1, 0.2, 0.2], documentId: "d")
        marquees.add([0.5, 0.5, 0.2, 0.2], documentId: "d")
        marquees.selectedIndex = 0
        marquees.removeSelected()
        XCTAssertEqual(marquees.rects, [[0.5, 0.5, 0.2, 0.2]])
        XCTAssertNil(marquees.selectedIndex)
        // Removing the last one empties the seam completely.
        marquees.selectedIndex = 0
        marquees.removeSelected()
        XCTAssertTrue(marquees.isEmpty)
        XCTAssertNil(marquees.documentId)
    }

    func testReadingOrderTopToBottomThenLeftToRight() {
        let rects: [[Double]] = [
            [0.6, 0.5, 0.1, 0.1],   // lower row, right
            [0.2, 0.1, 0.1, 0.1],   // top row
            [0.1, 0.5, 0.1, 0.1]    // lower row, left
        ]
        let ordered = PreviewMarqueeSelection.readingOrder(rects)
        XCTAssertEqual(ordered, [
            [0.2, 0.1, 0.1, 0.1],
            [0.1, 0.5, 0.1, 0.1],
            [0.6, 0.5, 0.1, 0.1]
        ])
    }

    // MARK: - Display ladder carries indices

    func testDisplayIndexedBoxesKeepFullListIndices() {
        let geometry = OCRGeometry(
            text: "",
            provider: "apple_vision",
            model: nil,
            boxes: [
                OCRGeometryBox(
                    text: "a line", bbox: [0.1, 0.1, 0.5, 0.05], level: "line",
                    confidence: nil, pageIndex: nil, charStart: nil, charEnd: nil
                ),
                OCRGeometryBox(
                    text: "word", bbox: [0.1, 0.1, 0.1, 0.05], level: "word",
                    confidence: nil, pageIndex: nil, charStart: nil, charEnd: nil
                ),
                OCRGeometryBox(
                    text: "word2", bbox: [0.3, 0.1, 0.1, 0.05], level: "word",
                    confidence: nil, pageIndex: nil, charStart: nil, charEnd: nil
                )
            ],
            renditionId: nil
        )
        let displayed = geometry.displayIndexedBoxes
        // Words win, and they keep their FULL-list positions (1 and 2), not
        // a renumbered 0 and 1 — the index is the engine's address.
        XCTAssertEqual(displayed.map(\.index), [1, 2])
    }

    func testDisplayIndexedBoxesFallBackToRegionsWhenNoWordsOrLines() {
        let geometry = OCRGeometry(
            text: "",
            provider: "user",
            model: nil,
            boxes: [
                OCRGeometryBox(
                    text: "", bbox: [0.1, 0.1, 0.2, 0.2], level: "region",
                    confidence: nil, pageIndex: nil, charStart: nil, charEnd: nil
                )
            ],
            renditionId: nil
        )
        XCTAssertEqual(geometry.displayIndexedBoxes.map(\.index), [0],
                       "a geometry of only hand-drawn regions must not render as nothing")
    }
}
