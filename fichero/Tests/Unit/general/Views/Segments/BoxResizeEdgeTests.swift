@testable import Fichero
import XCTest

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.edges-drag-and-say-so` (#6735). A press on
/// the length of a box's edge (not only its midpoint handle) grabs that edge and moves it on its one axis; a corner moves
/// two; the cursor over each says which. What breaks without this: only a tiny midpoint handle on a thin line box can be
/// hit, and the pointer gives no hint that an edge can be dragged.
final class BoxResizeEdgeTests: XCTestCase {
    private let box = [0.2, 0.3, 0.4, 0.05]
    private let reach = [0.01, 0.01]

    func testAPressAlongAnEdgeGrabsThatEdge() {
        XCTAssertEqual(BoxResize.grab(at: [0.25, 0.3], of: box, reach: reach), 3, "top edge, away from its midpoint")
        XCTAssertEqual(BoxResize.grab(at: [0.55, 0.35], of: box, reach: reach), 4, "bottom edge")
        XCTAssertEqual(BoxResize.grab(at: [0.2, 0.32], of: box, reach: reach), 1, "left edge")
        XCTAssertEqual(BoxResize.grab(at: [0.6, 0.32], of: box, reach: reach), 6, "right edge")
    }

    func testACornerBeatsTheEdgesThatMeetThere() {
        XCTAssertEqual(BoxResize.grab(at: [0.6, 0.35], of: box, reach: reach), 7)
        XCTAssertEqual(BoxResize.grab(at: [0.2, 0.3], of: box, reach: reach), 0)
    }

    func testThePointInsideOrFarOutsideGrabsNothing() {
        XCTAssertNil(BoxResize.grab(at: [0.4, 0.325], of: box, reach: reach), "inside, clear of every edge")
        XCTAssertNil(BoxResize.grab(at: [0.9, 0.9], of: box, reach: reach))
    }

    func testAnEdgeDragChangesOneAxisOnly() {
        let top = BoxResize.resized(box, handle: 3, to: [0.9, 0.25])
        XCTAssertEqual(top[0], 0.2, accuracy: 1e-9)
        XCTAssertEqual(top[2], 0.4, accuracy: 1e-9)
        XCTAssertEqual(top[1], 0.25, accuracy: 1e-9)
        XCTAssertEqual(top[3], 0.1, accuracy: 1e-9)
    }

    func testSeveralBoxesMoveTheSameEdgeByTheSameAmount() {
        let other = [0.1, 0.5, 0.2, 0.05]
        let moved = BoxResize.resizedTogether([box, other], handle: 6, by: [0.05, 0.2])
        XCTAssertEqual(moved[0][2], 0.45, accuracy: 1e-9)
        XCTAssertEqual(moved[1][2], 0.25, accuracy: 1e-9)
        XCTAssertEqual(moved[0][3], 0.05, accuracy: 1e-9, "the other axis is untouched")
    }

    func testTheCursorSaysWhichWayTheEdgeMoves() {
        XCTAssertEqual(BoxResize.cursor(overHandle: nil), .arrow)
        XCTAssertEqual(BoxResize.cursor(overHandle: 1), .leftRight)
        XCTAssertEqual(BoxResize.cursor(overHandle: 6), .leftRight)
        XCTAssertEqual(BoxResize.cursor(overHandle: 3), .upDown)
        XCTAssertEqual(BoxResize.cursor(overHandle: 4), .upDown)
        XCTAssertEqual(BoxResize.cursor(overHandle: 0), .diagonal)
        XCTAssertEqual(BoxResize.cursor(overHandle: 7), .diagonal)
    }

    /// The owner's report: a corner drag moved the box. A press on each corner grabs that corner, the drag resizes with
    /// the opposite corner fixed, and only a press inside the box (clear of the edges) grabs nothing, so it moves.
    func testACornerDragResizesWithTheOppositeCornerFixed() {
        let corners: [(handle: Int, press: [Double], fixed: [Double])] = [
            (0, [0.2, 0.3], [0.6, 0.35]), (2, [0.2, 0.35], [0.6, 0.3]),
            (5, [0.6, 0.3], [0.2, 0.35]), (7, [0.6, 0.35], [0.2, 0.3])
        ]
        for corner in corners {
            XCTAssertEqual(BoxResize.grab(at: corner.press, of: box, reach: reach), corner.handle)
            let target = [corner.press[0] + (corner.press[0] < 0.4 ? -0.05 : 0.05), corner.press[1] + (corner.press[1] < 0.325 ? -0.05 : 0.05)]
            let grown = BoxResize.resized(box, handle: corner.handle, to: target)
            let opposite = [corner.fixed[0] == grown[0] ? grown[0] : grown[0] + grown[2],
                            corner.fixed[1] == grown[1] ? grown[1] : grown[1] + grown[3]]
            XCTAssertEqual(opposite[0], corner.fixed[0], accuracy: 1e-9, "handle \(corner.handle): opposite x stays")
            XCTAssertEqual(opposite[1], corner.fixed[1], accuracy: 1e-9, "handle \(corner.handle): opposite y stays")
            XCTAssertEqual(grown[2], box[2] + 0.05, accuracy: 1e-9)
            XCTAssertEqual(grown[3], box[3] + 0.05, accuracy: 1e-9)
        }
        XCTAssertNil(BoxResize.grab(at: [0.4, 0.325], of: box, reach: reach), "inside: a move, not a resize")
    }
}
