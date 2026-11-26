@testable import Fichero
import Foundation
import Testing

/// #7082: a polygon drawn with the Shape tool closes by a double-click, Return or a click on its first point,
/// Esc cancels, and fewer than three points says why and makes nothing. What breaks without these: the polygon
/// can be started but not finished, or a refused close is silent.
@MainActor
@Suite(.tags(.paleography))
struct ShapeDrawingClosesTests {
    private let three: [[Double]] = [[0.1, 0.1], [0.3, 0.1], [0.3, 0.2]]

    private func drawing(_ points: [[Double]], kind: SegmentShapes.DrawKind = .polygon) -> WindowState {
        let state = WindowState(libraryId: LibraryManager.globalLibraryId)
        state.shapeKind = kind
        state.drawingPoints = points
        return state
    }

    @Test("Return or a double-click with three points hands them over and ends the drawing")
    func closesWithEnoughPoints() {
        let state = drawing(three)
        #expect(state.closeDrawing() == three)
        #expect(state.drawingPoints.isEmpty)
        #expect(state.segmentNotice == nil)
    }

    @Test("a baseline closes with two points")
    func baselineClosesWithTwo() {
        let state = drawing(Array(three.prefix(2)), kind: .baseline)
        #expect(state.closeDrawing() == Array(three.prefix(2)))
    }

    @Test("fewer than three points makes nothing and says why, keeping the points")
    func tooFewSaysWhy() {
        let state = drawing(Array(three.prefix(2)))
        #expect(state.closeDrawing() == nil)
        #expect(state.segmentNotice == "A polygon needs at least 3 points")
        #expect(state.drawingPoints.count == 2)
    }

    @Test("Return with nothing drawn is not a close and says nothing")
    func nothingDrawn() {
        let state = drawing([])
        #expect(state.closeDrawing() == nil)
        #expect(state.segmentNotice == nil)
    }

    @Test("a click on the first point closes a polygon of three or more")
    func firstPointCloses() {
        #expect(SegmentShapes.closes(three, at: [0.1005, 0.0998], tolerance: [0.004, 0.004]))
        #expect(!SegmentShapes.closes(Array(three.prefix(2)), at: [0.1, 0.1], tolerance: [0.004, 0.004]))
    }

    @Test("Esc cancels the drawing and makes nothing")
    func escapeCancels() {
        let state = drawing(three)
        #expect(state.abandonDrawing())
        #expect(state.drawingPoints.isEmpty)
    }

    @Test("double-click zoom stands aside while a polygon or baseline is clicked out, and only then")
    func doubleClickZoomStandsAside() {
        #expect(SegmentShapes.clicksPlacePoints(kind: .polygon, isEditing: true))
        #expect(SegmentShapes.clicksPlacePoints(kind: .baseline, isEditing: true))
        #expect(!SegmentShapes.clicksPlacePoints(kind: .box, isEditing: true))
        #expect(!SegmentShapes.clicksPlacePoints(kind: .polygon, isEditing: false))
    }
}
