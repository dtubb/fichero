@testable import Fichero
import SwiftUI
import XCTest

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.expand-one-axis` (#6735, owner ruling
/// 2026-11-21). Dragging a handle with ⇧ held changes one axis, the one the drag first moves along; the other edges stay;
/// without ⇧ the drag is as before; the release is one move, so one undo. What breaks without this: ⇧ does nothing, or
/// moves the edge on the axis that was not meant.
final class BoxResizeAxisTests: XCTestCase {
    private let box = [0.2, 0.3, 0.4, 0.2]

    func testTheAxisIsTheLargerFirstMoveOnceItIsPastTheThreshold() {
        XCTAssertNil(BoxResize.axis(from: [0.5, 0.5], to: [0.501, 0.501]), "too small to tell")
        XCTAssertEqual(BoxResize.axis(from: [0.5, 0.5], to: [0.5, 0.6]), .vertical)
        XCTAssertEqual(BoxResize.axis(from: [0.5, 0.5], to: [0.4, 0.51]), .horizontal)
    }

    func testAVerticalResizeLeavesXAndWidth() {
        let corner = BoxResize.resized(box, handle: 7, to: [0.9, 0.8], axis: .vertical)
        XCTAssertEqual(corner[0], 0.2, accuracy: 1e-9)
        XCTAssertEqual(corner[2], 0.4, accuracy: 1e-9)
        XCTAssertEqual(corner[1], 0.3, accuracy: 1e-9)
        XCTAssertEqual(corner[3], 0.5, accuracy: 1e-9)
    }

    func testAHorizontalResizeLeavesYAndHeight() {
        let corner = BoxResize.resized(box, handle: 7, to: [0.9, 0.8], axis: .horizontal)
        XCTAssertEqual(corner[1], 0.3, accuracy: 1e-9)
        XCTAssertEqual(corner[3], 0.2, accuracy: 1e-9)
        XCTAssertEqual(corner[0], 0.2, accuracy: 1e-9)
        XCTAssertEqual(corner[2], 0.7, accuracy: 1e-9)
    }

    func testNoAxisIsTheResizeAsBefore() {
        XCTAssertEqual(BoxResize.resized(box, handle: 7, to: [0.9, 0.8]), BoxResize.resized(box, handle: 7, to: [0.9, 0.8], axis: nil))
        XCTAssertEqual(BoxResize.resized(box, handle: 7, to: [0.9, 0.8]).map { ($0 * 1000).rounded() }, [200, 300, 700, 500])
    }
}

#if os(macOS)
@MainActor
final class ShiftDragOneAxisPointerTests: XCTestCase {
    private let size = CGSize(width: 400, height: 300)
    private let line = OCRGeometryBox(text: "a", bbox: [0.2, 0.3, 0.4, 0.2], level: "line", confidence: nil)

    private final class Commits {
        var moves: [(Int, [Double])] = []
    }

    /// Press the bottom-right handle of the one selected box and drag through `path`, ⇧ held or not.
    private func drag(through path: [(Double, Double)], shift: Bool) async throws -> [(Int, [Double])] {
        let commits = Commits()
        let selection = RegionSelection()
        selection.select(0, artifactId: "art", documentId: "page", in: [line])
        let feed = PreviewPointerFeed()
        let layer = RegionInteractionLayer(
            boxes: [(index: 0, box: line)], allBoxes: [line], visible: CGRect(x: 0, y: 0, width: 1, height: 1),
            artifactId: "art", documentId: "page", marquees: nil, imagePixelSize: nil, isAddingRegion: false,
            drawsSelection: false, pointer: feed,
            onMoveCommit: { commits.moves.append(($0, $1)) }, onPromote: { _, _ in }, onOpenRegion: { _ in },
            selection: selection
        )
        let state = WindowState(libraryId: UUID())
        state.isEditingSegments = true
        let window = NSWindow(contentRect: CGRect(origin: CGPoint(x: 100, y: 100), size: size),
                              styleMask: [.borderless], backing: .buffered, defer: false)
        let host = NSHostingView(rootView: layer.environment(state).frame(width: size.width, height: size.height))
        window.contentView = host
        defer { window.contentView = nil }
        host.layoutSubtreeIfNeeded()
        try await Task.sleep(nanoseconds: 50_000_000)
        var events = [PreviewPointerEvent(phase: .pressed, point: CGPoint(x: 0.6, y: 0.5), shift: shift, clickCount: 1)]
        events += path.map { PreviewPointerEvent(phase: .dragged, point: CGPoint(x: $0.0, y: $0.1), shift: shift, clickCount: 1) }
        let last = path[path.count - 1]
        events.append(PreviewPointerEvent(phase: .released, point: CGPoint(x: last.0, y: last.1), shift: shift, clickCount: 1))
        for event in events {
            feed.publish(event)
            for _ in 0..<5 {
                host.layoutSubtreeIfNeeded()
                try await Task.sleep(nanoseconds: 10_000_000)
            }
        }
        return commits.moves
    }

    func testAShiftDragThatStartsVerticalChangesOnlyYAndHeight() async throws {
        let moves = try await drag(through: [(0.602, 0.6), (0.8, 0.7)], shift: true)
        XCTAssertEqual(moves.count, 1, "one move, one undo")
        let box = try XCTUnwrap(moves.first).1
        XCTAssertEqual(box[0], 0.2, accuracy: 0.001)
        XCTAssertEqual(box[2], 0.4, accuracy: 0.001, "x and width unchanged")
        XCTAssertEqual(box[3], 0.4, accuracy: 0.001, "the bottom edge went to 0.7")
    }

    func testAShiftDragThatStartsHorizontalChangesOnlyXAndWidth() async throws {
        let moves = try await drag(through: [(0.7, 0.502), (0.8, 0.9)], shift: true)
        XCTAssertEqual(moves.count, 1)
        let box = try XCTUnwrap(moves.first).1
        XCTAssertEqual(box[1], 0.3, accuracy: 0.001)
        XCTAssertEqual(box[3], 0.2, accuracy: 0.001, "y and height unchanged")
        XCTAssertEqual(box[2], 0.6, accuracy: 0.001, "the right edge went to 0.8")
    }

    func testWithoutShiftBothEdgesMove() async throws {
        let moves = try await drag(through: [(0.7, 0.6), (0.8, 0.7)], shift: false)
        let box = try XCTUnwrap(moves.first).1
        XCTAssertEqual(box[2], 0.6, accuracy: 0.001)
        XCTAssertEqual(box[3], 0.4, accuracy: 0.001)
    }
}
#endif
