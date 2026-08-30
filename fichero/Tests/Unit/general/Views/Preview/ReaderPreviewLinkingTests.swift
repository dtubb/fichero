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

// Cross-document anchoring (2026-08-23): the reader shows an ENTRY, the
// preview shows its source PAGE — the ids never match, so the selection's
// TEXT locates it in the page's transcript.
extension ReaderPreviewLinkingTests {
    @Test("selected text anchors in the page transcript, UTF-16 offsets")
    func textAnchor() {
        let page = "At Dredge No 4 all day. Bedenbacker, electrician, hurt this afternoon."
        let range = geometryRange(of: "Bedenbacker, electrician", in: page)
        #expect(range == 24..<48)
        // Case/diacritic-insensitive; a lie-proof nil for the unfindable.
        #expect(geometryRange(of: "BEDENBACKER, ELECTRICIAN", in: page) == 24..<48)
        #expect(geometryRange(of: "not on this page", in: page) == nil)
        #expect(geometryRange(of: "at", in: page) == nil)  // < 3 chars = too ambiguous
    }
}
