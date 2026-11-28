@testable import Fichero
import SwiftUI
import XCTest

#if os(macOS)
/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.every-tool-works` (#7034). With the Region
/// tool armed in Edit Segments, a dragged box is handed to the host to save as a segment on the shown pass (selected,
/// undoable there); it is not left as a marquee promoted through the regions-artifact route. What breaks without this:
/// the drag makes no region a person can see on a segment pass.
@MainActor
final class DrawRegionPointerTests: XCTestCase {
    private let size = CGSize(width: 400, height: 300)

    private final class Calls {
        var drawn: [[Double]] = []
        var promoted = 0
        var polygons = 0
    }

    func testARegionDragInEditSegmentsHandsTheBoxToTheHostOnce() async throws {
        let calls = Calls()
        let feed = PreviewPointerFeed()
        var layer = RegionInteractionLayer(
            boxes: [], allBoxes: [], visible: CGRect(x: 0, y: 0, width: 1, height: 1), artifactId: nil,
            documentId: "page", marquees: PreviewMarqueeSelection(), imagePixelSize: nil, isAddingRegion: true,
            drawsSelection: false, drawsSegments: true, pointer: feed,
            onMoveCommit: { _, _ in }, onPromote: { _, _ in calls.promoted += 1 }, onOpenRegion: { _ in },
            selection: RegionSelection()
        )
        layer.onDrawRegionBox = { calls.drawn.append($0) }
        let state = WindowState(libraryId: UUID())
        state.isEditingSegments = true
        let window = NSWindow(contentRect: CGRect(origin: CGPoint(x: 100, y: 100), size: size),
                              styleMask: [.borderless], backing: .buffered, defer: false)
        let host = NSHostingView(rootView: layer.environment(state).frame(width: size.width, height: size.height))
        window.contentView = host
        defer { window.contentView = nil }
        host.layoutSubtreeIfNeeded()
        try await Task.sleep(nanoseconds: 50_000_000)
        let steps: [(PreviewPointerPhase, CGPoint)] = [
            (.pressed, CGPoint(x: 0.1, y: 0.2)), (.dragged, CGPoint(x: 0.3, y: 0.4)),
            (.dragged, CGPoint(x: 0.5, y: 0.6)), (.released, CGPoint(x: 0.5, y: 0.6))
        ]
        for (phase, point) in steps {
            feed.publish(PreviewPointerEvent(phase: phase, point: point, shift: false, clickCount: 1))
            for _ in 0..<5 {
                host.layoutSubtreeIfNeeded()
                try await Task.sleep(nanoseconds: 10_000_000)
            }
        }
        XCTAssertEqual(calls.drawn.count, 1, "one drag, one region")
        let box = try XCTUnwrap(calls.drawn.first)
        XCTAssertEqual(box[0], 0.1, accuracy: 0.01)
        XCTAssertEqual(box[1], 0.2, accuracy: 0.01)
        XCTAssertEqual(box[2], 0.4, accuracy: 0.01)
        XCTAssertEqual(box[3], 0.4, accuracy: 0.01)
        XCTAssertEqual(calls.promoted, 0, "not left as a marquee promoted through the regions artifact")
    }

    /// `segment-editor.draw-a-line` (#7083): the Line tool (the polygon tool at the Line level) draws a line box or a
    /// polygon. The steps are fed to a layer whose tool draws polygons at `level` (the Makes picker's choice; nil
    /// follows the selection); what comes back is the boxes handed to the host, the polygons committed, and the points
    /// still being drawn.
    private func feedPolygonTool(
        _ steps: [(PreviewPointerPhase, CGPoint)], level: SegmentShapes.DrawnLevel? = .line
    ) async throws -> (calls: Calls, points: [[Double]]) {
        let calls = Calls()
        let feed = PreviewPointerFeed()
        var layer = RegionInteractionLayer(
            boxes: [], allBoxes: [], visible: CGRect(x: 0, y: 0, width: 1, height: 1), artifactId: nil,
            documentId: "page", marquees: PreviewMarqueeSelection(), imagePixelSize: nil, isAddingRegion: true,
            drawsSelection: false, drawsSegments: true, pointer: feed,
            onMoveCommit: { _, _ in }, onPromote: { _, _ in calls.promoted += 1 }, onOpenRegion: { _ in },
            selection: RegionSelection()
        )
        layer.drawKind = .polygon
        layer.onDrawShapeCommit = { _, _ in calls.polygons += 1 }
        layer.onDrawRegionBox = { calls.drawn.append($0) }
        let state = WindowState(libraryId: UUID())
        state.isEditingSegments = true
        state.shapeKind = .polygon
        state.drawnLevel = level
        let window = NSWindow(contentRect: CGRect(origin: CGPoint(x: 100, y: 100), size: size),
                              styleMask: [.borderless], backing: .buffered, defer: false)
        let host = NSHostingView(rootView: layer.environment(state).frame(width: size.width, height: size.height))
        window.contentView = host
        defer { window.contentView = nil }
        host.layoutSubtreeIfNeeded()
        try await Task.sleep(nanoseconds: 50_000_000)
        for (phase, point) in steps {
            feed.publish(PreviewPointerEvent(phase: phase, point: point, shift: false, clickCount: 1))
            for _ in 0..<5 {
                host.layoutSubtreeIfNeeded()
                try await Task.sleep(nanoseconds: 10_000_000)
            }
        }
        XCTAssertEqual(calls.promoted, 0)
        return (calls, state.drawingPoints)
    }

    func testADragWithThePolygonToolHandsOneBoxToTheHostAndLeavesNoPoint() async throws {
        let made = try await feedPolygonTool([
            (.pressed, CGPoint(x: 0.1, y: 0.2)), (.dragged, CGPoint(x: 0.3, y: 0.4)),
            (.dragged, CGPoint(x: 0.5, y: 0.6)), (.released, CGPoint(x: 0.5, y: 0.6))
        ])
        XCTAssertEqual(made.calls.drawn.count, 1, "one drag, one box")
        let box = try XCTUnwrap(made.calls.drawn.first)
        XCTAssertEqual(box[0], 0.1, accuracy: 0.01)
        XCTAssertEqual(box[1], 0.2, accuracy: 0.01)
        XCTAssertEqual(box[2], 0.4, accuracy: 0.01)
        XCTAssertEqual(box[3], 0.4, accuracy: 0.01)
        XCTAssertEqual(made.points, [], "the press was the box's corner, not a polygon's first point")
        XCTAssertEqual(made.calls.polygons, 0)
    }

    func testClicksWithThePolygonToolStillPlacePointsAndADragAfterTheFirstMakesNoBox() async throws {
        let made = try await feedPolygonTool([
            (.pressed, CGPoint(x: 0.1, y: 0.2)), (.released, CGPoint(x: 0.1, y: 0.2)),
            (.pressed, CGPoint(x: 0.5, y: 0.2)), (.dragged, CGPoint(x: 0.7, y: 0.6)), (.released, CGPoint(x: 0.7, y: 0.6))
        ])
        XCTAssertEqual(made.calls.drawn.count, 0, "only the first point can begin a box")
        XCTAssertEqual(made.points.count, 2, "each click placed its point")
        XCTAssertEqual(made.calls.polygons, 0)
    }

    /// `source.editor.draw-shapes`: away from the Line level the Polygon tool is clicks only, so a drag from its first
    /// point makes no box and the press stays the polygon's first point.
    func testADragWithThePolygonToolAwayFromTheLineLevelMakesNoBoxAndKeepsThePoint() async throws {
        for level in [SegmentShapes.DrawnLevel.region, .word, nil] {
            let made = try await feedPolygonTool([
                (.pressed, CGPoint(x: 0.1, y: 0.2)), (.dragged, CGPoint(x: 0.3, y: 0.4)),
                (.dragged, CGPoint(x: 0.5, y: 0.6)), (.released, CGPoint(x: 0.5, y: 0.6))
            ], level: level)
            let name = level?.rawValue ?? "follow selection"
            XCTAssertEqual(made.calls.drawn.count, 0, "\(name): only the Line level drags a box")
            XCTAssertEqual(made.points.count, 1, "\(name): the press placed the first point")
            XCTAssertEqual(made.calls.polygons, 0)
        }
    }

    func testOnlyAPolygonsFirstPointAtTheLineLevelWhereBoxesAreSavedBeginsABox() {
        XCTAssertTrue(SegmentShapes.firstPointStartsBox(kind: .polygon, level: .line, placed: 0, savesBoxes: true))
        XCTAssertFalse(SegmentShapes.firstPointStartsBox(kind: .polygon, level: .region, placed: 0, savesBoxes: true))
        XCTAssertFalse(SegmentShapes.firstPointStartsBox(kind: .polygon, level: .word, placed: 0, savesBoxes: true))
        XCTAssertFalse(SegmentShapes.firstPointStartsBox(kind: .polygon, level: nil, placed: 0, savesBoxes: true))
        XCTAssertFalse(SegmentShapes.firstPointStartsBox(kind: .polygon, level: .line, placed: 1, savesBoxes: true))
        XCTAssertFalse(SegmentShapes.firstPointStartsBox(kind: .baseline, level: .line, placed: 0, savesBoxes: true))
        XCTAssertFalse(SegmentShapes.firstPointStartsBox(kind: .polygon, level: .line, placed: 0, savesBoxes: false))
    }
}
#endif
