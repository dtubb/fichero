@testable import Fichero
import Testing

/// #6183: a ⌥-dragged box makes a segment; Escape during the drag makes nothing.
@Suite("Make a new segment in the Preview (#6183)")
@MainActor
struct PreviewMakeNewSegmentTests {
    @Test("Escape during a ⌥-dragged box abandons it, once")
    func escapeAbandonsTheBox() {
        let windowState = WindowState()
        windowState.boxDrawing = true
        #expect(windowState.abandonDrawing())
        #expect(!windowState.boxDrawing)
        #expect(!windowState.abandonDrawing())
    }

    @Test("a box is the corners of its rect, and a line is one baseline across its middle")
    func boxCorners() {
        #expect(SegmentShapes.corners(ofRect: [0.1, 0.2, 0.3, 0.1]).count == 4)
        #expect(SegmentShapes.DrawKind.baseline.minimumPoints == 2)
    }

    @Test("the pointer event carries ⌥ and ⌃ apart, so the lasso (⌃) and the box (⌥) do not collide")
    func modifiersApart() {
        let event = PreviewPointerEvent(phase: .pressed, point: .zero, shift: false, clickCount: 1, option: true)
        #expect(event.option && !event.control)
    }
}
