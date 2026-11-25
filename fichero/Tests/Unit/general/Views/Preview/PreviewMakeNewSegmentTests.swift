@testable import Fichero
import Testing

@Suite("Make a new segment in the Preview (#6183)")
@MainActor
struct PreviewMakeNewSegmentTests {
    @Test("Escape during a ⌥-dragged box abandons it, once")
    func escapeAbandonsTheBox() {
        let windowState = WindowState(libraryId: LibraryManager.globalLibraryId)
        windowState.boxDrawing = true
        #expect(windowState.abandonDrawing())
        #expect(!windowState.boxDrawing)
        #expect(!windowState.abandonDrawing())
    }

    @Test("the pointer event carries ⌥ and ⌃ apart, so the lasso (⌃) and the box (⌥) do not collide")
    func modifiersApart() {
        let event = PreviewPointerEvent(phase: .pressed, point: .zero, shift: false, clickCount: 1, option: true)
        #expect(event.option && !event.control)
    }
}
