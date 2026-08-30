@testable import Fichero
import Foundation
import XCTest

/// Pure canvas math (#4322/#4323): drop-location inverse transform and
/// parallel-edge separation offsets.
final class WorkflowCanvasMathTests: XCTestCase {

    private let canvasSize = CGSize(width: 2000, height: 1500)

    // MARK: - Drop-location inverse transform

    func testIdentityTransformIsPassThrough() {
        let point = WorkflowCanvasTransform.canvasPoint(
            fromDropLocation: CGPoint(x: 320, y: 240),
            canvasSize: canvasSize,
            scale: 1.0,
            offset: .zero
        )
        XCTAssertEqual(point.x, 320, accuracy: 0.001)
        XCTAssertEqual(point.y, 240, accuracy: 0.001)
    }

    func testCenterIsFixedPointOfPureZoom() {
        // scaleEffect anchors at the frame center, so the center maps to itself.
        let center = CGPoint(x: canvasSize.width / 2, y: canvasSize.height / 2)
        let point = WorkflowCanvasTransform.canvasPoint(
            fromDropLocation: center,
            canvasSize: canvasSize,
            scale: 2.0,
            offset: .zero
        )
        XCTAssertEqual(point.x, center.x, accuracy: 0.001)
        XCTAssertEqual(point.y, center.y, accuracy: 0.001)
    }

    func testInverseUndoesForwardTransform() {
        // Forward: q = center + (p − center)·scale + offset. The inverse must
        // recover p exactly for arbitrary zoom + pan.
        let canvasPoint = CGPoint(x: 450, y: 900)
        let scale: CGFloat = 1.7
        let offset = CGSize(width: -120, height: 65)
        let center = CGPoint(x: canvasSize.width / 2, y: canvasSize.height / 2)
        let transformed = CGPoint(
            x: center.x + (canvasPoint.x - center.x) * scale + offset.width,
            y: center.y + (canvasPoint.y - center.y) * scale + offset.height
        )

        let recovered = WorkflowCanvasTransform.canvasPoint(
            fromDropLocation: transformed,
            canvasSize: canvasSize,
            scale: scale,
            offset: offset
        )
        XCTAssertEqual(recovered.x, canvasPoint.x, accuracy: 0.001)
        XCTAssertEqual(recovered.y, canvasPoint.y, accuracy: 0.001)
    }

    func testPanOnlyShiftsByOffset() {
        let point = WorkflowCanvasTransform.canvasPoint(
            fromDropLocation: CGPoint(x: 100, y: 100),
            canvasSize: canvasSize,
            scale: 1.0,
            offset: CGSize(width: 40, height: -30)
        )
        XCTAssertEqual(point.x, 60, accuracy: 0.001)
        XCTAssertEqual(point.y, 130, accuracy: 0.001)
    }

    func testZeroScaleDoesNotDivideByZero() {
        let point = WorkflowCanvasTransform.canvasPoint(
            fromDropLocation: CGPoint(x: 10, y: 10),
            canvasSize: canvasSize,
            scale: 0,
            offset: .zero
        )
        XCTAssertTrue(point.x.isFinite)
        XCTAssertTrue(point.y.isFinite)
    }

    // MARK: - Parallel edge offsets

    private func segment(_ id: String, from: CGPoint, to: CGPoint) -> EdgeParallelOffset.Segment {
        EdgeParallelOffset.Segment(id: id, source: from, target: to)
    }

    func testUniqueGeometryGetsNoOffset() {
        let offsets = EdgeParallelOffset.offsets(for: [
            segment("a", from: CGPoint(x: 0, y: 0), to: CGPoint(x: 100, y: 0)),
            segment("b", from: CGPoint(x: 0, y: 50), to: CGPoint(x: 100, y: 50))
        ])
        XCTAssertTrue(offsets.isEmpty)
    }

    func testTwoCoincidentEdgesFanSymmetrically() {
        let from = CGPoint(x: 0, y: 0)
        let to = CGPoint(x: 100, y: 0)
        let offsets = EdgeParallelOffset.offsets(
            for: [segment("a", from: from, to: to), segment("b", from: from, to: to)],
            spacing: 12
        )
        XCTAssertEqual(offsets["a"], -6)
        XCTAssertEqual(offsets["b"], 6)
    }

    func testThreeCoincidentEdgesCenterTheMiddleOne() {
        let from = CGPoint(x: 0, y: 0)
        let to = CGPoint(x: 100, y: 0)
        let offsets = EdgeParallelOffset.offsets(
            for: ["a", "b", "c"].map { segment($0, from: from, to: to) },
            spacing: 10
        )
        XCTAssertEqual(offsets["a"], -10)
        XCTAssertEqual(offsets["b"], 0)
        XCTAssertEqual(offsets["c"], 10)
    }

    func testSharedSourceDifferentTargetIsNotOffset() {
        // A fan from one port to two different nodes must NOT be perturbed —
        // only fully coincident geometry separates.
        let from = CGPoint(x: 0, y: 0)
        let offsets = EdgeParallelOffset.offsets(for: [
            segment("a", from: from, to: CGPoint(x: 100, y: -40)),
            segment("b", from: from, to: CGPoint(x: 100, y: 40))
        ])
        XCTAssertTrue(offsets.isEmpty)
    }
}
