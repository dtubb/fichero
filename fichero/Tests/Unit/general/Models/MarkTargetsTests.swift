@testable import Fichero
import Testing

/// Q6 (ruled 2026-09-27): a mark made on the selection is attached to the selected segments it is
/// drawn over. What breaks without these: a highlight strip on line 2 attached to every selected line
/// (so deleting line 1 drags the mark along), or to none (so it drifts when a box moves).
struct MarkTargetsTests {
    private let selected: [(id: String, rect: [Double])] = [
        (id: "line-2", rect: [0.1, 0.30, 0.8, 0.05]),
        (id: "line-1", rect: [0.1, 0.20, 0.8, 0.05]),
        (id: "margin", rect: [0.92, 0.20, 0.05, 0.30])
    ]

    @Test("a strip is attached to the selected segments it is drawn over, in the order picked")
    func stripTakesTheSegmentsItCovers() {
        #expect(MarkTargets.segmentIds(in: [0.1, 0.30, 0.5, 0.05], selected: selected) == ["line-2"])
        #expect(MarkTargets.segmentIds(in: [0.05, 0.19, 0.9, 0.2], selected: selected) == ["line-2", "line-1"])
    }

    /// From the imported Syriac page: line 1's box reaches ~5% into line 2's.
    @Test("a strip on one line is not attached to the neighbour its box merely overlaps")
    func aNeighboursSlightOverlapIsNotAttached() {
        let lines: [(id: String, rect: [Double])] = [
            (id: "line-1", rect: [0.1097, 0.6825, 0.6938, 0.0465]),
            (id: "line-2", rect: [0.1117, 0.7264, 0.6887, 0.0499])
        ]
        #expect(MarkTargets.segmentIds(in: lines[0].rect, selected: lines) == ["line-1"])
        #expect(MarkTargets.segmentIds(in: lines[1].rect, selected: lines) == ["line-2"])
    }

    @Test("boxes that only touch the strip's edge, or lie outside it, are not attached")
    func edgesAndOutsideAreNot() {
        #expect(MarkTargets.segmentIds(in: [0.1, 0.25, 0.5, 0.05], selected: selected).isEmpty)
        #expect(MarkTargets.segmentIds(in: [0.0, 0.9, 1.0, 0.05], selected: selected).isEmpty)
        #expect(MarkTargets.segmentIds(in: [], selected: selected).isEmpty)
    }
}
