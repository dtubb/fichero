@testable import Fichero
import Testing

// Reader → preview word linking: char-span interval overlap, not containment.
struct ReaderPreviewLinkingTests {
    private func geometry(_ spans: [(Int, Int)]) -> OCRGeometry {
        OCRGeometry(
            text: "x", provider: "apple", model: nil,
            boxes: spans.enumerated().map { idx, span in
                OCRGeometryBox(
                    text: "w\(idx)", bbox: [Double(idx), 0, 1, 1], level: "word",
                    confidence: nil, pageIndex: nil,
                    charStart: span.0, charEnd: span.1
                )
            },
            renditionId: nil
        )
    }

    @Test("overlap lights the word; adjacency does not")
    func overlapRule() {
        let geo = geometry([(0, 5), (6, 11), (12, 17)])
        // Selecting chars 3..<8 clips words 1 and 2, misses word 3.
        #expect(wordBoxes(intersecting: 3..<8, in: geo).map { $0[0] } == [0, 1])
        // A selection ending exactly where a word starts does not light it.
        #expect(wordBoxes(intersecting: 0..<6, in: geo).map { $0[0] } == [0])
    }

    @Test("empty selection, derived boxes without spans, and line boxes stay dark")
    func gates() {
        let geo = geometry([(0, 5)])
        #expect(wordBoxes(intersecting: 2..<2, in: geo).isEmpty)
        var spanless = geo
        spanless.boxes[0].charStart = nil
        #expect(wordBoxes(intersecting: 0..<5, in: spanless).isEmpty)
    }
}
