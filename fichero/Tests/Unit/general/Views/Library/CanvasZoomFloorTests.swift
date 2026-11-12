import CoreGraphics
@testable import Fichero
import Foundation
import simd
import Testing

/// spec: library-view-modes `library.canvas.zoom-out-stops-near-fit` (#6368). The pure rule: the
/// furthest zoom-out is the fit pose's scale over 0.9, follows the pane and the board, and an empty
/// board has a one-cell floor instead of the old fixed 200.
struct CanvasZoomFloorTests {
    // The board's own units (a cell is about 1.15 x 0.9, `CanvasGridPlacement`): in the 100-point units this test
    // first used, a 4x3 board's fit (270) was past the renderer's ceiling (200) and the rule answered the ceiling.
    private let margin: Float = 0.5
    private let emptyScale: Float = 0.63
    private let ceiling: Float = 200

    /// 12 cards of 1.0x1.4 in a 4x3 grid, pitch 1.5.
    private var board: [CanvasCameraFit.Card] {
        (0..<12).map { index in
            CanvasCameraFit.Card(
                center: SIMD2(Float(index % 4) * 1.5, Float(index / 4) * 1.5), size: SIMD2(1.0, 1.4)
            )
        }
    }

    private func farthest(_ cards: [CanvasCameraFit.Card], _ viewport: CGSize) -> Float {
        CanvasCameraFit.maxOrthoScale(
            cards, viewport: viewport, margin: margin, emptyBoardScale: emptyScale, ceiling: ceiling
        )
    }

    @Test("the furthest zoom-out is the fit pose's scale over 0.9, with every card in view")
    func floorIsFitOverNinetyPercent() throws {
        let viewport = CGSize(width: 1000, height: 700)
        let pose = try #require(CanvasCameraFit.fit(board, viewport: viewport, margin: margin))
        let limit = farthest(board, viewport)
        #expect(abs(limit - pose.orthoScale / 0.9) < 0.001)
        // At that scale the whole board still fits the pane.
        let shown = CanvasCameraFit.Pose(center: pose.center, orthoScale: limit)
        #expect(CanvasCameraFit.shows(shown, board, viewport: viewport))
        #expect(limit > pose.orthoScale)
    }

    @Test("a smaller pane raises the furthest zoom-out to that pane's own fit")
    func floorFollowsThePane() throws {
        let big = farthest(board, CGSize(width: 1000, height: 700))
        let small = farthest(board, CGSize(width: 500, height: 350))
        let smallPose = try #require(CanvasCameraFit.fit(board, viewport: CGSize(width: 500, height: 350), margin: margin))
        #expect(small >= big)
        #expect(abs(small - smallPose.orthoScale / 0.9) < 0.001)
    }

    @Test("adding a card that widens the board raises the furthest zoom-out")
    func floorFollowsTheBoard() {
        let viewport = CGSize(width: 1000, height: 700)
        let wider = board + [CanvasCameraFit.Card(center: SIMD2(20, 0), size: SIMD2(1.0, 1.4))]
        #expect(farthest(wider, viewport) > farthest(board, viewport))
    }

    @Test("an empty board uses the one-cell floor, not the fixed 200")
    func emptyBoardFloor() {
        #expect(farthest([], CGSize(width: 1000, height: 700)) == emptyScale)
        #expect(farthest([], CGSize(width: 500, height: 350)) == emptyScale)
    }

    @Test("the floor never exceeds the renderer's own ceiling")
    func neverAboveTheCeiling() {
        let huge = [CanvasCameraFit.Card(center: .zero, size: SIMD2(100_000, 100_000))]
        #expect(farthest(huge, CGSize(width: 1000, height: 700)) == ceiling)
    }

    @Test("zooming in is unchanged: the near limit stays 0.1")
    func nearLimitUnchanged() {
        #expect(CanvasOrtho2DRenderer.minOrthoScale == 0.1)
        #expect(CanvasOrtho2DRenderer.maxOrthoScaleCeiling == 200)
    }
}
