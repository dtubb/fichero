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

    @Test("words still take over when the page has them")
    func wordsTakeOver() {
        let geometry = OCRGeometry(text: "", provider: "ocr", model: nil,
                                   boxes: [box("region", 0.1), box("line", 0.1), box("word", 0.1), box("word", 0.2)])
        #expect(geometry.displayIndexedBoxes.map(\.index) == [2, 3])
    }

    @Test("a region is drawn lighter than the lines over it, and at full strength alone")
    func regionsLighter() {
        let region = DocumentOverlay.Box(bbox: [0.1, 0.1, 0.5, 0.3], confidence: nil, kind: "region")
        let line = DocumentOverlay.Box(bbox: [0.1, 0.1, 0.5, 0.05], confidence: nil, kind: "line")
        let both = DocumentOverlay(boxes: [region, line])
        #expect(both.showsLines)
        #expect(DocumentOverlay.strength(ofKind: region.kind, linesShown: both.showsLines) < 1)
        #expect(DocumentOverlay.strength(ofKind: line.kind, linesShown: both.showsLines) == 1)
        let alone = DocumentOverlay(boxes: [region])
        #expect(DocumentOverlay.strength(ofKind: region.kind, linesShown: alone.showsLines) == 1, "a page of regions alone is not faded")
    }
}
