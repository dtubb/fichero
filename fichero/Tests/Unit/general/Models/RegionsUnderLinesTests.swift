@testable import Fichero
import Testing

/// #5284, `source.editor.regions-under-lines`, ruled 2026-10-01: a page with regions and lines draws
/// both, the regions lighter. The preview drew only the finest level a page had, so the moment a page
/// had lines its regions were never on screen (the imported Syriac page: 4 regions, 12 lines, 12
/// drawn). What breaks without these: the regions vanish again, the boxes are renumbered (the index
/// is how the engine addresses a box for curation), or the regions compete with the lines at full
/// strength.
struct RegionsUnderLinesTests {
    private func box(_ level: String, _ y: Double) -> OCRGeometryBox {
        OCRGeometryBox(text: level, bbox: [0.1, y, 0.5, 0.05], level: level, confidence: nil)
    }

    @Test("a page with regions and lines draws both, each at its own index")
    func regionsAndLines() {
        let geometry = OCRGeometry(text: "", provider: "page", model: nil,
                                   boxes: [box("region", 0.1), box("line", 0.1), box("line", 0.2), box("region", 0.5), box("line", 0.5)])
        let shown = geometry.displayIndexedBoxes
        #expect(shown.map(\.index) == [0, 1, 2, 3, 4])
        #expect(shown.filter { $0.box.level == "region" }.count == 2)
    }

    // Superseded 2026-10-05 (hierarchy A, #5426): words no longer take over -- a page with words draws its
    // regions and lines under them -- and a region is no longer faded under its lines: each child is drawn
    // lighter than its PARENT. Pinned now by `SegmentHierarchyTests`, through the store.
    @Test("words no longer hide the lines and regions they sit in")
    func wordsKeepTheirParents() {
        let geometry = OCRGeometry(text: "", provider: "ocr", model: nil,
                                   boxes: [box("region", 0.1), box("line", 0.1), box("word", 0.1), box("word", 0.2)])
        #expect(geometry.displayIndexedBoxes.map(\.index) == [0, 1, 2, 3])
    }

    @Test("a line is drawn lighter than its region, and a region alone at full strength")
    func linesLighterThanTheirRegion() {
        #expect(SegmentHierarchy.strokeOpacity(level: .line, toneStrength: 1)
            < SegmentHierarchy.strokeOpacity(level: .region, toneStrength: 1))
        #expect(SegmentHierarchy.strokeOpacity(level: .region, toneStrength: 1) == 1, "a region is not faded")
    }
}
