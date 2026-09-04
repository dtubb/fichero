@testable import Fichero
import Testing

/// Box-gated marking (Daniel, 2026-09-04): highlight / underline /
/// strikethrough / star anchor only to text that HAS a bounding box. The
/// word-snap is mandatory for those kinds; a drag over box-less canvas
/// yields NOTHING, and the caller refuses with a quiet reason instead of
/// minting an unanchored mark.
struct AnnotationBoxGateTests {

    private func box(
        _ bbox: [Double], level: String = "word", text: String = "w"
    ) -> OCRGeometryBox {
        OCRGeometryBox(
            text: text, bbox: bbox, level: level,
            confidence: nil, pageIndex: nil, charStart: nil, charEnd: nil,
            provider: nil, source: nil
        )
    }

    @Test("a drag touching words snaps to per-line strips, as before")
    func dragTouchingWordsSnaps() {
        let words = [
            box([0.20, 0.10, 0.10, 0.03]),
            box([0.32, 0.10, 0.10, 0.03]),
            box([0.20, 0.20, 0.10, 0.03])
        ]
        let lines = [
            box([0.18, 0.095, 0.60, 0.04], level: "line"),
            box([0.18, 0.195, 0.60, 0.04], level: "line")
        ]
        let strips = AnnotationWordSnap.gatedRects(
            drag: [0.19, 0.09, 0.30, 0.05], words: words, lines: lines
        )
        #expect(strips.count == 1, "a one-line drag yields one strip")
        // Normalized geometry is Double, and the strip's width is computed as
        // maxX - minX, so `minX + width` is a subtract-then-add round trip:
        // 0.20 + 0.22000000000000003, which is not 0.42 on any machine. The
        // SNAP is exact — the strip really does end at the second word's right
        // edge — the equality was not. Compared within a tolerance far tighter
        // than a pixel at any zoom, so a real drift still fails.
        #expect(abs(strips[0][0] - 0.20) < 1e-9, "the strip hugs the touched words")
        #expect(abs((strips[0][0] + strips[0][2]) - 0.42) < 1e-9, "the strip hugs the touched words")
    }

    @Test("a lines-only geometry still anchors: the touched LINE boxes win")
    func linesOnlyGeometryAnchorsToLines() {
        let lines = [
            box([0.2, 0.10, 0.6, 0.03], level: "line"),
            box([0.2, 0.20, 0.6, 0.03], level: "line"),
            box([0.2, 0.30, 0.6, 0.03], level: "line")
        ]
        let strips = AnnotationWordSnap.gatedRects(
            drag: [0.25, 0.09, 0.3, 0.13], words: [], lines: lines
        )
        #expect(strips == [[0.2, 0.10, 0.6, 0.03], [0.2, 0.20, 0.6, 0.03]], "the two touched lines, in reading order")
    }

    @Test("a drag over box-less canvas yields NOTHING — the refusal signal")
    func boxlessDragYieldsNothing() {
        let words = [box([0.20, 0.10, 0.10, 0.03])]
        let lines = [box([0.18, 0.095, 0.60, 0.04], level: "line")]
        let strips = AnnotationWordSnap.gatedRects(
            drag: [0.10, 0.70, 0.20, 0.10], words: words, lines: lines
        )
        #expect(strips.isEmpty, "no words, no lines under the drag: no mark")
    }

    @Test("an empty geometry yields NOTHING for gated kinds")
    func emptyGeometryYieldsNothing() {
        let strips = AnnotationWordSnap.gatedRects(
            drag: [0.1, 0.1, 0.5, 0.2], words: [], lines: []
        )
        #expect(strips.isEmpty, "no geometry at all: no anchored mark to make")
    }
}
