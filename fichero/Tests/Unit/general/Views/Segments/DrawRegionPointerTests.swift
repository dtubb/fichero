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
}
#endif
