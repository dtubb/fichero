import CoreGraphics
@testable import Fichero
import Testing

/// Preview.app's selection (#5215): eight handles that resize, the shapes carried with the frame. What
/// breaks without these: a handle drags a different edge than the one drawn under the pointer, a box
/// inverts when dragged past its opposite edge, or a resize moves a polygon without scaling it (or a plain
/// move starts scaling one).
struct BoxResizeTests {
    private let box = [0.2, 0.3, 0.4, 0.2]  // x 0.2...0.6, y 0.3...0.5

    #if os(macOS)
    @Test("the handles are where SelectionStyle draws them, in the same order")
    func sameHandlesAsDrawn() {
        let drawn = SelectionStyle.handleRects(around: CGRect(x: 0.2, y: 0.3, width: 0.4, height: 0.2), side: 0)
        for (index, rect) in drawn.enumerated() {
            let place = BoxResize.position(of: index, on: box)
            #expect(abs(place[0] - rect.midX) < 1e-9 && abs(place[1] - rect.midY) < 1e-9, "handle \(index)")
        }
    }
    #endif

    @Test("a corner moves two edges, an edge midpoint one, and the rest stay")
    func resize() {
        // Handle 7: the bottom-right corner.
        #expect(BoxResize.resized(box, handle: 7, to: [0.7, 0.6]).map { ($0 * 1000).rounded() } == [200, 300, 500, 300])
        // Handle 1: the left edge's midpoint; y is untouched whatever the pointer's y.
        #expect(BoxResize.resized(box, handle: 1, to: [0.1, 0.9]).map { ($0 * 1000).rounded() } == [100, 300, 500, 200])
    }

    @Test("dragged past the opposite edge the box flips, never inverts, and never goes below the minimum")
    func flipAndMinimum() {
        let flipped = BoxResize.resized(box, handle: 6, to: [0.1, 0.4])  // right edge dragged left of the left
        #expect(flipped.map { ($0 * 1000).rounded() } == [100, 300, 100, 200])
        let flat = BoxResize.resized(box, handle: 6, to: [0.2, 0.4])
        #expect(flat[2] == 0.002, "a box never collapses to nothing")
    }

    @Test("a press finds the handle under it within a handle's reach, else nothing")
    func hit() {
        #expect(BoxResize.handle(at: [0.601, 0.499], of: box, reach: [0.005, 0.005]) == 7)
        #expect(BoxResize.handle(at: [0.4, 0.4], of: box, reach: [0.005, 0.005]) == nil, "inside is a move, not a resize")
    }

    @Test("a move shifts the shapes; a resize scales them with the frame")
    func shapesCarried() {
        let point = [0.4, 0.4]  // the middle of the box
        let shifted = SegmentEdit.mapped(point, from: box, to: [0.3, 0.3, 0.4, 0.2])
        #expect(abs(shifted[0] - 0.5) < 1e-9 && abs(shifted[1] - 0.4) < 1e-9, "same size: a pure shift")
        let scaled = SegmentEdit.mapped(point, from: box, to: [0.2, 0.3, 0.8, 0.4])
        #expect(abs(scaled[0] - 0.6) < 1e-9 && abs(scaled[1] - 0.5) < 1e-9, "still the middle of the bigger box")
    }
}
