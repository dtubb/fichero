@testable import Fichero
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.select-brush`. The Brush selects every
/// segment its paint touches (a stroke of points, each the brush's radius), at the level being edited; `[` and `]` change
/// its size; B held is one stroke and a tap of B chooses it. What breaks without these: a brush that misses a line it
/// visibly covers, one that grabs a line beyond its radius, or a size that runs away.
@MainActor
@Suite(.tags(.paleography))
struct BrushSelectTests {
    typealias Gestures = SegmentSelectionGestures
    private let page: [Gestures.Box] = [
        .init(index: 0, bbox: [0.0, 0.0, 1.0, 1.0], level: "region"),
        .init(index: 1, bbox: [0.1, 0.10, 0.5, 0.04], level: "line"),
        .init(index: 2, bbox: [0.1, 0.20, 0.5, 0.04], level: "line"),
        .init(index: 3, bbox: [0.1, 0.30, 0.5, 0.04], level: "line")
    ]

    @Test("a stroke down the margin selects the lines it touches and not one just beyond its radius")
    func touches() {
        let stroke: [[Double]] = [[0.08, 0.12], [0.08, 0.18], [0.08, 0.22]]
        #expect(Gestures.touched(by: stroke, radius: [0.03, 0.03], boxes: page, level: "line") == [1, 2])
        #expect(Gestures.touched(by: stroke, radius: [0.01, 0.01], boxes: page, level: "line").isEmpty,
                "two hundredths from the lines' edge is out of a one-hundredth brush")
        #expect(Gestures.touched(by: [], radius: [0.03, 0.03], boxes: page, level: "line").isEmpty)
    }

    @Test("the radius is per axis: a round brush on a tall page reaches further across than down")
    func ellipse() {
        let dot: [[Double]] = [[0.65, 0.22]]
        #expect(Gestures.touched(by: dot, radius: [0.06, 0.01], boxes: page, level: "line") == [2])
        #expect(Gestures.touched(by: dot, radius: [0.01, 0.06], boxes: page, level: "line").isEmpty)
    }

    @Test("[ and ] change the size within its bounds; a tap of B chooses the Brush and puts the others down")
    func sizeAndKey() {
        let window = WindowState(libraryId: UUID())
        for _ in 0..<30 { window.resizeBrush(larger: true) }
        #expect(window.brushSize == 120)
        for _ in 0..<30 { window.resizeBrush(larger: false) }
        #expect(window.brushSize == 6)
        window.knifeArmed = true
        window.pressBrushKey()
        window.letGoOfBrushKey()
        #expect(window.brushArmed)
        #expect(!window.knifeArmed)
        window.activeMarkupTool = .drawRegion
        #expect(!window.brushArmed, "another tool puts the Brush down")
    }
}
