@testable import Fichero
import XCTest

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.edges-move-by-key` (#6735). ⌥-arrow moves
/// the edge on the arrow's side in the arrow's direction (the box grows); ⌃⌥-arrow moves that edge back (the box shrinks);
/// 1 image pixel a press, 10 with ⇧, on every selected box; never past the page and never thinner than the minimum.
/// What breaks without this: a keypress that pushes a box off the page or collapses it.
final class EdgeKeysTests: XCTestCase {
    private let page = [1000.0, 500.0]
    private let box = [0.2, 0.3, 0.4, 0.1]

    func testOptionRightMovesTheRightEdgeOutByOnePixel() {
        let grown = EdgeKeys.plan([box], side: .right, outward: true, pixels: 1, imagePixels: page)
        XCTAssertEqual(grown[0][2], 0.401, accuracy: 1e-9)
        XCTAssertEqual(grown[0][0], 0.2, accuracy: 1e-9)
    }

    func testControlOptionMovesTheSameEdgeBack() {
        let shrunk = EdgeKeys.plan([box], side: .down, outward: false, pixels: 10, imagePixels: page)
        XCTAssertEqual(shrunk[0][3], 0.08, accuracy: 1e-9)
        XCTAssertEqual(shrunk[0][1], 0.3, accuracy: 1e-9)
    }

    func testTheLeftAndTopEdgesMoveTheOriginAsTheyGrow() {
        let left = EdgeKeys.plan([box], side: .left, outward: true, pixels: 10, imagePixels: page)
        XCTAssertEqual(left[0][0], 0.19, accuracy: 1e-9)
        XCTAssertEqual(left[0][2], 0.41, accuracy: 1e-9)
        let top = EdgeKeys.plan([box], side: .up, outward: true, pixels: 10, imagePixels: page)
        XCTAssertEqual(top[0][1], 0.28, accuracy: 1e-9)
        XCTAssertEqual(top[0][3], 0.12, accuracy: 1e-9)
    }

    func testEverySelectedBoxMoves() {
        let other = [0.1, 0.6, 0.2, 0.1]
        let grown = EdgeKeys.plan([box, other], side: .right, outward: true, pixels: 10, imagePixels: page)
        XCTAssertEqual(grown[0][2], 0.41, accuracy: 1e-9)
        XCTAssertEqual(grown[1][2], 0.21, accuracy: 1e-9)
    }

    func testTheEdgeStopsAtThePage() {
        let near = [0.5, 0.3, 0.495, 0.1]
        let grown = EdgeKeys.plan([near], side: .right, outward: true, pixels: 10, imagePixels: page)
        XCTAssertEqual(grown[0][0] + grown[0][2], 1.0, accuracy: 1e-9)
        let edge = [0.004, 0.3, 0.4, 0.1]
        let left = EdgeKeys.plan([edge], side: .left, outward: true, pixels: 10, imagePixels: page)
        XCTAssertEqual(left[0][0], 0, accuracy: 1e-9)
        XCTAssertEqual(left[0][0] + left[0][2], 0.404, accuracy: 1e-9, "the other edge stays")
    }

    func testABoxIsNeverMadeThinnerThanTheMinimum() {
        let thin = [0.2, 0.3, 0.003, 0.1]
        let shrunk = EdgeKeys.plan([thin], side: .right, outward: false, pixels: 10, imagePixels: page)
        XCTAssertEqual(shrunk, [thin], "a press that would pass the minimum changes nothing")
    }
}
